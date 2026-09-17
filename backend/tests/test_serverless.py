"""Settings and endpoints that let the API run on a serverless host (Vercel)."""

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Settings, get_settings
from app.scheduler import jobs
from app.services.rate_limit import client_ip

SECRET = "s" * 40


def test_run_jobs_needs_the_cron_secret(client: TestClient, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(jobs, "run_due_jobs", lambda: calls.append(1) or {"expire_stale_bookings": "ok"})

    monkeypatch.setattr(get_settings(), "cron_secret", "")
    assert client.get("/internal/run-jobs", headers={"Authorization": "Bearer "}).status_code == 401  # disabled

    monkeypatch.setattr(get_settings(), "cron_secret", SECRET)
    assert client.get("/internal/run-jobs").status_code == 401
    assert client.get("/internal/run-jobs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert calls == []

    for method in ("GET", "POST"):
        response = client.request(method, "/internal/run-jobs", headers={"Authorization": f"Bearer {SECRET}"})
        assert response.status_code == 200
        assert response.json() == {"expire_stale_bookings": "ok"}
    assert len(calls) == 2


def test_a_failing_job_does_not_stop_the_others(monkeypatch) -> None:
    ran = []

    def boom() -> None:
        raise RuntimeError("smtp down")

    monkeypatch.setattr(jobs, "expire_stale_bookings_job", lambda: ran.append("expire"))
    monkeypatch.setattr(jobs, "complete_finished_bookings_job", boom)
    monkeypatch.setattr(jobs, "send_reminders_job", lambda: ran.append("reminders"))
    monkeypatch.setattr(jobs, "dispatch_notifications_job", lambda: ran.append("dispatch"))
    monkeypatch.setattr(jobs, "purge_rate_limits_job", lambda: ran.append("purge"))

    results = jobs.run_due_jobs()

    assert results["complete_finished_bookings"] == "failed"
    assert ran == ["expire", "reminders", "dispatch", "purge"]


def test_hosted_postgres_urls_use_the_psycopg_driver() -> None:
    for url in ("postgres://u:p@db.neon.tech/app?sslmode=require", "postgresql://u:p@db.neon.tech/app?sslmode=require"):
        assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@db.neon.tech/app?sslmode=require"
    assert Settings(database_url="postgresql+psycopg://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"


def test_client_ip_can_come_from_a_trusted_proxy_header(monkeypatch) -> None:
    request = Request(
        {"type": "http", "headers": [(b"x-real-ip", b"203.0.113.9")], "client": ("10.0.0.1", 1234)}
    )
    assert client_ip(request) == "10.0.0.1"
    monkeypatch.setattr(get_settings(), "client_ip_header", "x-real-ip")
    assert client_ip(request) == "203.0.113.9"


def test_serverless_entry_point_serves_the_api_under_api_prefix(client: TestClient) -> None:
    # `client` wires the test database into the shared FastAPI app that the mount wraps.
    from app.serverless import app as serverless_app

    with TestClient(serverless_app) as mounted:
        assert mounted.get("/api/health").json() == {"status": "ok", "database": "ok"}
        assert mounted.get("/api/webinars").status_code == 200
        assert mounted.get("/api/users/me").status_code == 401
        assert mounted.get("/health").status_code == 404


def test_vercel_requirements_match_the_backend_requirements() -> None:
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    root_file = backend_dir.parent / "requirements.txt"
    if not root_file.exists():  # the Docker test container only mounts backend/
        return

    def packages(path: Path) -> list[str]:
        lines = (line.split("#")[0].strip() for line in path.read_text().splitlines())
        return [line for line in lines if line]

    assert packages(root_file) == packages(backend_dir / "requirements.txt")


def test_claim_window_allows_one_caller_per_minute() -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    from app.database import engine
    from app.models import RateLimitCounter
    from app.services.rate_limit import claim_window

    scope = "test:claim-window"
    minute = datetime(2026, 9, 17, 10, 0, 5, tzinfo=UTC)
    try:
        assert claim_window(scope, timedelta(minutes=1), now=minute) is True
        assert claim_window(scope, timedelta(minutes=1), now=minute + timedelta(seconds=40)) is False
        assert claim_window(scope, timedelta(minutes=1), now=minute + timedelta(minutes=1)) is True
    finally:
        with engine.begin() as connection:  # counters are committed outside the test transaction
            connection.execute(delete(RateLimitCounter).where(RateLimitCounter.key == scope))


def test_tick_runs_the_jobs_only_when_enabled_and_this_minute_is_unclaimed(client: TestClient, monkeypatch) -> None:
    from app.services import rate_limit

    calls = []
    monkeypatch.setattr(jobs, "run_due_jobs", lambda: calls.append(1) or {"send_reminders": "ok"})
    claims = iter([True, False])
    monkeypatch.setattr(rate_limit, "claim_window", lambda scope, window: next(claims))

    monkeypatch.setattr(get_settings(), "jobs_tick_enabled", False)
    assert client.post("/internal/tick").json() == {"ran": False}
    assert calls == []

    monkeypatch.setattr(get_settings(), "jobs_tick_enabled", True)
    assert client.post("/internal/tick").json() == {"ran": True, "jobs": {"send_reminders": "ok"}}
    assert client.post("/internal/tick").json() == {"ran": False}
    assert calls == [1]
