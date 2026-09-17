"""Guards against accidentally exposing endpoints or weakening production settings."""

import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app, create_app

ANY_UUID = "00000000-0000-0000-0000-000000000000"

# Every route reachable without logging in. Adding to this list should be a deliberate decision.
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/reset-password"),
    ("GET", "/departments"),
    ("GET", "/departments/{department_id}"),
    ("GET", "/webinars"),
    ("GET", "/webinars/{webinar_id}"),
    ("GET", "/webinars/{webinar_id}/slots"),
    ("POST", "/payments/webhook"),  # authenticated by Razorpay's signature instead
    ("POST", "/internal/tick"),  # runs the jobs at most once a minute, whoever calls it
}


def api_routes() -> list[tuple[str, str]]:
    # Read from the OpenAPI schema: FastAPI nests included routers, so app.routes isn't flat.
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


def test_route_discovery_sees_the_whole_api() -> None:
    # Guards the checks below against passing vacuously if route discovery breaks.
    assert len(api_routes()) > 50


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", ANY_UUID, path)


def test_public_route_list_matches_the_app() -> None:
    assert PUBLIC_ROUTES <= set(api_routes()), "PUBLIC_ROUTES lists a route that no longer exists"


def test_every_other_route_requires_login(client: TestClient) -> None:
    unprotected = [
        (method, path)
        for method, path in api_routes()
        if (method, path) not in PUBLIC_ROUTES
        and client.request(method, concrete(path), json={}).status_code != 401
    ]

    assert unprotected == []


def test_admin_routes_reject_learners(client: TestClient, learner_headers: dict) -> None:
    admin_routes = [(m, p) for m, p in api_routes() if p.startswith("/admin")]
    assert len(admin_routes) > 20

    allowed = [
        (method, path)
        for method, path in admin_routes
        if client.request(method, concrete(path), json={}, headers=learner_headers).status_code != 403
    ]

    assert allowed == []


def test_security_headers_on_api_responses(client: TestClient) -> None:
    response = client.get("/webinars")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "Strict-Transport-Security" not in response.headers  # only when served over HTTPS


def test_oversized_request_bodies_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/login", content=b"x" * 1_000_001, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large."}


def test_unexpected_errors_do_not_leak_details() -> None:
    broken = create_app()

    @broken.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    response = TestClient(broken, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side. Please try again."}
    assert "hunter2" not in response.text


PRODUCTION = {
    "app_env": "production",
    "jwt_secret": "p" * 48,
    "cookie_secure": True,
    "cors_origins": "https://skillcortex.in",
    "frontend_url": "https://skillcortex.in",
    "rate_limit_enabled": True,  # the test environment turns limits off
    "database_url": "postgresql+psycopg://skill_cortex:skill_cortex@localhost:5432/skill_cortex_test",
}


def test_production_hides_api_docs_and_sends_hsts() -> None:
    production_client = TestClient(create_app(Settings(**PRODUCTION)))

    assert production_client.get("/docs").status_code == 404
    assert production_client.get("/openapi.json").status_code == 404
    assert production_client.get("/webinars/not-a-uuid").headers["Strict-Transport-Security"].startswith("max-age=")


@pytest.mark.parametrize(
    "override, problem",
    [
        ({"jwt_secret": "change-me"}, "JWT_SECRET"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED"),
        ({"frontend_url": "http://skillcortex.in"}, "FRONTEND_URL"),
    ],
)
def test_unsafe_production_settings_refuse_to_start(override: dict, problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        Settings(**(PRODUCTION | override))
