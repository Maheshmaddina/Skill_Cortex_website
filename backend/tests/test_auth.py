from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, RecordStatus, RefreshToken, User, UserRole
from app.routes.auth import REFRESH_COOKIE
from app.utils.security import hash_token, verify_password
from tests.factories import DEFAULT_PASSWORD, auth_header, make_department, make_user
from tests.fakes import FakeNotifier


def register_payload(department_id, **overrides) -> dict:
    payload = {
        "name": "Dhanushya",
        "email": "Dhanushya@Example.com",
        "phone": "+91 98765 43210",
        "password": "Secret123",
        "department_id": str(department_id),
    }
    return payload | overrides


def login(client: TestClient, email: str, password: str = DEFAULT_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def post_with_refresh_cookie(client: TestClient, path: str, raw_token: str):
    client.cookies.clear()
    return client.post(path, headers={"Cookie": f"{REFRESH_COOKIE}={raw_token}"})


# --- registration -----------------------------------------------------------


def test_register_creates_learner_account(client: TestClient, db: Session) -> None:
    department = make_department(db, "Data Science")

    response = client.post("/auth/register", json=register_payload(department.id))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "dhanushya@example.com"
    assert body["phone"] == "9876543210"
    assert body["role"] == "USER"
    assert body["department"]["name"] == "Data Science"
    assert "password_hash" not in body

    user = db.scalar(select(User).where(User.email == "dhanushya@example.com"))
    assert user.password_hash != "Secret123"
    assert verify_password("Secret123", user.password_hash)


def test_register_rejects_duplicate_email_case_insensitively(client: TestClient, db: Session) -> None:
    department = make_department(db)
    make_user(db, email="dhanushya@example.com")

    response = client.post("/auth/register", json=register_payload(department.id))

    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists."


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"phone": "12345"},
        {"phone": "5876543210"},  # Indian mobiles start with 6-9
        {"password": "Short1"},
        {"password": "onlyletters"},
        {"password": "1234567890"},
        {"name": " "},
    ],
)
def test_register_validates_input(client: TestClient, db: Session, overrides: dict) -> None:
    department = make_department(db)

    response = client.post("/auth/register", json=register_payload(department.id, **overrides))

    assert response.status_code == 422


def test_register_rejects_inactive_department(client: TestClient, db: Session) -> None:
    department = make_department(db)
    department.status = RecordStatus.INACTIVE
    db.flush()

    response = client.post("/auth/register", json=register_payload(department.id))

    assert response.status_code == 400
    assert response.json()["detail"] == "Selected department is not available."


# --- login / current user -------------------------------------------------------


def test_login_returns_access_token_and_httponly_refresh_cookie(client: TestClient, db: Session) -> None:
    user = make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)

    response = login(client, "LEARNER@example.com")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["id"] == str(user.id)
    set_cookie = response.headers["set-cookie"]
    assert f"{REFRESH_COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/auth" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    me = client.get("/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "learner@example.com"


def test_wrong_password_and_unknown_email_get_the_same_error(client: TestClient, db: Session) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)

    wrong_password = login(client, "learner@example.com", "Wrong-pass1")
    unknown_email = login(client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {"detail": "Email or password is incorrect."}


def test_disabled_account_cannot_log_in(client: TestClient, db: Session) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD, is_active=False)

    assert login(client, "learner@example.com").status_code == 403


def test_me_rejects_missing_invalid_and_expired_tokens(client: TestClient, db: Session) -> None:
    user = make_user(db)
    expired = jwt.encode(
        {"sub": str(user.id), "type": "access", "role": "USER", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": str(user.id), "type": "access", "role": "ADMIN", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "some-other-secret-that-is-long-enough-000000000",
        algorithm="HS256",
    )

    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/users/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    assert client.get("/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_update_me_changes_profile_and_department(client: TestClient, db: Session) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")
    user = make_user(db, department=cse)

    response = client.put(
        "/users/me",
        headers=auth_header(user),
        json={"name": "New Name", "phone": "9123456789", "department_id": str(data_science.id)},
    )

    assert response.status_code == 200
    assert response.json()["department"]["name"] == "Data Science"
    assert response.json()["phone"] == "9123456789"
    assert user.name == "New Name"


# --- refresh / logout -----------------------------------------------------------


def test_refresh_rotates_token_and_detects_reuse(client: TestClient, db: Session) -> None:
    user = make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    first_token = login(client, "learner@example.com").cookies[REFRESH_COOKIE]

    rotated = post_with_refresh_cookie(client, "/auth/refresh", first_token)
    assert rotated.status_code == 200
    assert rotated.json()["access_token"]
    second_token = rotated.cookies[REFRESH_COOKIE]
    assert second_token != first_token

    # Replaying the old token well after rotation is treated as theft: it fails and the newer session is revoked too.
    old = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(first_token)))
    old.revoked_at -= timedelta(minutes=1)
    db.flush()
    assert post_with_refresh_cookie(client, "/auth/refresh", first_token).status_code == 401
    assert post_with_refresh_cookie(client, "/auth/refresh", second_token).status_code == 401
    active = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).all()
    assert active == []


def test_near_simultaneous_refresh_from_two_tabs_does_not_end_the_session(client: TestClient, db: Session) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    token = login(client, "learner@example.com").cookies[REFRESH_COOKIE]

    first_tab = post_with_refresh_cookie(client, "/auth/refresh", token)
    second_tab = post_with_refresh_cookie(client, "/auth/refresh", token)  # same old cookie, moments later

    assert first_tab.status_code == 200
    assert second_tab.status_code == 401
    # The first tab's new session is still valid.
    assert post_with_refresh_cookie(client, "/auth/refresh", first_tab.cookies[REFRESH_COOKIE]).status_code == 200


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, db: Session) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    token = login(client, "learner@example.com").cookies[REFRESH_COOKIE]

    logout = post_with_refresh_cookie(client, "/auth/logout", token)

    assert logout.status_code == 204
    assert f'{REFRESH_COOKIE}=""' in logout.headers["set-cookie"] or "Max-Age=0" in logout.headers["set-cookie"]
    assert post_with_refresh_cookie(client, "/auth/refresh", token).status_code == 401


# --- password reset -------------------------------------------------------------


@pytest.fixture
def sent_reset_links(notifier: FakeNotifier) -> list[str]:
    return notifier.reset_links


def test_forgot_password_does_not_reveal_whether_account_exists(
    client: TestClient, db: Session, sent_reset_links: list[str]
) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)

    known = client.post("/auth/forgot-password", json={"email": "learner@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(sent_reset_links) == 1


def test_reset_password_flow(client: TestClient, db: Session, sent_reset_links: list[str]) -> None:
    user = make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    refresh_token = login(client, "learner@example.com").cookies[REFRESH_COOKIE]
    client.post("/auth/forgot-password", json={"email": "learner@example.com"})
    token = sent_reset_links[0].split("token=")[1]

    response = client.post("/auth/reset-password", json={"token": token, "new_password": "BrandNew123"})

    assert response.status_code == 200
    assert login(client, "learner@example.com", "BrandNew123").status_code == 200
    assert login(client, "learner@example.com", DEFAULT_PASSWORD).status_code == 401
    # Link is single-use, and sessions from before the reset are ended.
    reuse = client.post("/auth/reset-password", json={"token": token, "new_password": "Another123"})
    assert reuse.status_code == 400
    assert post_with_refresh_cookie(client, "/auth/refresh", refresh_token).status_code == 401
    assert user.id is not None


def test_only_latest_reset_link_works(client: TestClient, db: Session, sent_reset_links: list[str]) -> None:
    make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    client.post("/auth/forgot-password", json={"email": "learner@example.com"})
    client.post("/auth/forgot-password", json={"email": "learner@example.com"})
    old_token, new_token = (link.split("token=")[1] for link in sent_reset_links)

    assert client.post("/auth/reset-password", json={"token": old_token, "new_password": "BrandNew123"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": new_token, "new_password": "BrandNew123"}).status_code == 200


def test_expired_reset_link_is_rejected(client: TestClient, db: Session, sent_reset_links: list[str]) -> None:
    user = make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    client.post("/auth/forgot-password", json={"email": "learner@example.com"})
    token = sent_reset_links[0].split("token=")[1]
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    reset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    response = client.post("/auth/reset-password", json={"token": token, "new_password": "BrandNew123"})

    assert response.status_code == 400
    assert response.json()["detail"] == "This password reset link is invalid or has expired."


# --- departments (public, used by the registration form) ------------------------


def test_public_departments_list_only_active(client: TestClient, db: Session) -> None:
    active = make_department(db, "Active dept")
    inactive = make_department(db, "Inactive dept")
    inactive.status = RecordStatus.INACTIVE
    db.flush()

    names = [d["name"] for d in client.get("/departments").json()]

    assert "Active dept" in names
    assert "Inactive dept" not in names
    assert client.get(f"/departments/{active.id}").status_code == 200
    assert client.get(f"/departments/{inactive.id}").status_code == 404


def test_admin_role_is_not_self_assignable(client: TestClient, db: Session) -> None:
    department = make_department(db)

    response = client.post("/auth/register", json=register_payload(department.id, role="ADMIN"))

    assert response.status_code == 201
    assert response.json()["role"] == UserRole.USER
