from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import AdminUser
from app.models import UserRole
from app.scripts.create_admin import AdminCreationError, create_admin
from app.utils.security import verify_password
from tests.factories import DEFAULT_PASSWORD, auth_header, make_user


@pytest.fixture
def admin_client(db: Session) -> Iterator[TestClient]:
    """A throwaway app with one admin-only route, so the guard is tested independently of real admin routes."""
    guarded = FastAPI()

    @guarded.get("/admin/ping")
    def ping(admin: AdminUser) -> dict[str, str]:
        return {"admin": admin.email}

    guarded.dependency_overrides[get_db] = lambda: db
    with TestClient(guarded) as test_client:
        yield test_client


def test_admin_routes_require_admin_role(admin_client: TestClient, db: Session) -> None:
    learner = make_user(db)
    admin = make_user(db, role=UserRole.ADMIN)

    assert admin_client.get("/admin/ping").status_code == 401
    assert admin_client.get("/admin/ping", headers=auth_header(learner)).status_code == 403
    assert admin_client.get("/admin/ping", headers=auth_header(admin)).status_code == 200


def test_demoted_admin_loses_access_immediately(admin_client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    headers = auth_header(admin)  # token still says ADMIN

    admin.role = UserRole.USER
    db.flush()

    assert admin_client.get("/admin/ping", headers=headers).status_code == 403


def test_create_admin_script_creates_admin_without_department(db: Session) -> None:
    admin = create_admin(
        db, name="Skill Cortex Admin", email="Admin@SkillCortex.in", phone="9876543210", password=DEFAULT_PASSWORD
    )

    assert admin.role == UserRole.ADMIN
    assert admin.email == "admin@skillcortex.in"
    assert admin.department_id is None
    assert verify_password(DEFAULT_PASSWORD, admin.password_hash)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"password": "weak"}, "at least 8"),
        ({"phone": "123"}, "Indian mobile"),
        ({"email": "nope"}, "email"),
    ],
)
def test_create_admin_script_validates_input(db: Session, overrides: dict, message: str) -> None:
    args = {"name": "Admin", "email": "admin@skillcortex.in", "phone": "9876543210", "password": DEFAULT_PASSWORD}

    with pytest.raises(AdminCreationError, match=message):
        create_admin(db, **(args | overrides))


def test_create_admin_script_rejects_existing_email(db: Session) -> None:
    make_user(db, email="admin@skillcortex.in")

    with pytest.raises(AdminCreationError, match="already exists"):
        create_admin(db, name="Admin", email="ADMIN@skillcortex.in", phone="9876543210", password=DEFAULT_PASSWORD)
