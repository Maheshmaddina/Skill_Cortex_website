"""Fixed-window rate limits stored in Postgres.

Counters live in the database so limits hold across several API workers, and each hit is
committed on its own connection so it still counts when the request itself fails and is
rolled back (e.g. a wrong password). Identifiers (IPs, emails, user ids) are stored hashed.

Per-IP limits are generous because many learners may share one campus NAT address; the
per-account limits are the tight ones.
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.database import engine
from app.models import RateLimitCounter
from app.services.errors import ServiceError


class RateLimited(ServiceError):
    status_code = 429

    def __init__(self, retry_after_seconds: int) -> None:
        minutes = max(1, math.ceil(retry_after_seconds / 60))
        super().__init__(f"Too many attempts. Please try again in {minutes} minute{'' if minutes == 1 else 's'}.")
        self.headers = {"Retry-After": str(retry_after_seconds)}


@dataclass(frozen=True)
class Limit:
    scope: str
    max_hits: int
    window: timedelta


LOGIN_PER_ACCOUNT = Limit("login:account", 10, timedelta(minutes=15))
LOGIN_PER_IP = Limit("login:ip", 100, timedelta(minutes=15))
REGISTER_PER_IP = Limit("register:ip", 50, timedelta(hours=1))
FORGOT_PASSWORD_PER_ACCOUNT = Limit("forgot:account", 3, timedelta(hours=1))
FORGOT_PASSWORD_PER_IP = Limit("forgot:ip", 30, timedelta(hours=1))
RESET_PASSWORD_PER_IP = Limit("reset:ip", 20, timedelta(minutes=15))
REFRESH_PER_IP = Limit("refresh:ip", 300, timedelta(minutes=5))
BOOKINGS_PER_USER = Limit("bookings:user", 30, timedelta(minutes=10))
PAYMENTS_PER_USER = Limit("payments:user", 30, timedelta(minutes=10))


def client_ip(request: Request) -> str:
    """The connecting client's address. Behind a reverse proxy, run uvicorn with
    --proxy-headers --forwarded-allow-ips=<proxy ip> so this is the real client."""
    return request.client.host if request.client else "unknown"


def hit(limit: Limit, identifier: str, *, now: datetime | None = None) -> None:
    """Count one attempt; raise RateLimited once the window's allowance is used up."""
    if not get_settings().rate_limit_enabled:
        return
    now = now or datetime.now(UTC)
    window_seconds = int(limit.window.total_seconds())
    window_start = datetime.fromtimestamp(int(now.timestamp()) // window_seconds * window_seconds, UTC)
    window_end = window_start + limit.window
    key = f"{limit.scope}:{hashlib.sha256(identifier.encode()).hexdigest()[:40]}"

    statement = (
        insert(RateLimitCounter)
        .values(key=key, window_start=window_start, count=1, expires_at=window_end)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    with engine.begin() as connection:
        count = connection.execute(statement).scalar_one()

    if count > limit.max_hits:
        raise RateLimited(max(1, math.ceil((window_end - now).total_seconds())))


def purge_expired(now: datetime | None = None) -> int:
    with engine.begin() as connection:
        result = connection.execute(delete(RateLimitCounter).where(RateLimitCounter.expires_at <= (now or datetime.now(UTC))))
    return result.rowcount
