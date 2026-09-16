from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import RateLimitCounter
from app.services import rate_limit
from app.services.rate_limit import Limit, RateLimited
from tests.factories import DEFAULT_PASSWORD, auth_header, make_slot, make_user, make_webinar


@pytest.fixture
def rate_limits(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Counters are committed on their own connection, so clear them around each test."""
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    with engine.begin() as connection:
        connection.execute(delete(RateLimitCounter))
    yield
    with engine.begin() as connection:
        connection.execute(delete(RateLimitCounter))


def login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_is_limited_per_account_even_when_attempts_fail(client: TestClient, db: Session, rate_limits) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)

    for _ in range(rate_limit.LOGIN_PER_ACCOUNT.max_hits):
        assert login(client, "learner@example.com", "Wrong-guess1").status_code == 401

    blocked = login(client, "LEARNER@example.com", DEFAULT_PASSWORD)  # right password, but too late
    assert blocked.status_code == 429
    assert blocked.json()["detail"].startswith("Too many attempts. Please try again in")
    assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60
    # Other accounts are unaffected.
    assert login(client, "someone-else@example.com", "Wrong-guess1").status_code == 401


def test_forgot_password_is_limited_per_address_without_revealing_accounts(client: TestClient, rate_limits) -> None:
    statuses = [
        client.post("/auth/forgot-password", json={"email": "nobody@example.com"}).status_code
        for _ in range(rate_limit.FORGOT_PASSWORD_PER_ACCOUNT.max_hits + 1)
    ]

    assert statuses == [202, 202, 202, 429]


def test_booking_attempts_are_limited_per_learner(client: TestClient, db: Session, rate_limits, monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "BOOKINGS_PER_USER", Limit("bookings:user", 2, timedelta(minutes=10)))
    learner = make_user(db)
    slots = [make_slot(db, make_webinar(db)) for _ in range(3)]

    statuses = [
        client.post("/bookings", json={"slot_id": str(slot.id)}, headers=auth_header(learner)).status_code
        for slot in slots
    ]

    assert statuses == [201, 201, 429]


def test_counters_reset_in_the_next_window(rate_limits) -> None:
    limit = Limit("test:window", 2, timedelta(minutes=1))
    start = datetime(2026, 9, 14, 10, 0, 5, tzinfo=UTC)

    rate_limit.hit(limit, "client", now=start)
    rate_limit.hit(limit, "client", now=start + timedelta(seconds=10))
    with pytest.raises(RateLimited) as blocked:
        rate_limit.hit(limit, "client", now=start + timedelta(seconds=20))
    assert blocked.value.headers == {"Retry-After": "35"}

    rate_limit.hit(limit, "client", now=start + timedelta(minutes=1))  # new window


def test_identifiers_are_stored_hashed_and_expired_counters_purged(engine: Engine, rate_limits) -> None:
    now = datetime.now(UTC)
    rate_limit.hit(Limit("test:purge", 5, timedelta(minutes=1)), "learner@example.com", now=now - timedelta(hours=1))
    rate_limit.hit(Limit("test:keep", 5, timedelta(hours=2)), "learner@example.com", now=now)

    with engine.connect() as connection:
        keys = connection.scalars(select(RateLimitCounter.key)).all()
    assert all("learner@example.com" not in key for key in keys)

    assert rate_limit.purge_expired(now) == 1
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(RateLimitCounter)) == 1


def test_limits_can_be_switched_off(rate_limits, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    limit = Limit("test:off", 1, timedelta(minutes=1))

    for _ in range(5):
        rate_limit.hit(limit, "client")
