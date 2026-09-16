from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BookingStatus, PaymentStatus, RefreshToken, UserRole
from app.routes.auth import REFRESH_COOKIE
from app.utils.security import create_access_token
from tests.factories import (
    DEFAULT_PASSWORD,
    auth_header,
    make_booking,
    make_department,
    make_payment,
    make_slot,
    make_user,
    make_webinar,
)


def test_admin_lists_users_with_booking_totals(client: TestClient, db: Session) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")
    admin = make_user(db, email="admin@skillcortex.in", role=UserRole.ADMIN)
    dhanushya = make_user(db, email="dhanushya@example.com", department=cse)
    make_user(db, email="arjun@example.com", department=data_science, is_active=False)
    slot = make_slot(db, make_webinar(db))
    paid = make_booking(db, dhanushya, slot, BookingStatus.CONFIRMED)
    make_payment(db, paid, PaymentStatus.PAID)
    make_booking(db, dhanushya, make_slot(db, make_webinar(db)), BookingStatus.CANCELLED)
    headers = auth_header(admin)

    def emails(**params) -> list[str]:
        response = client.get("/admin/users", params=params, headers=headers)
        assert response.status_code == 200
        return sorted(item["email"] for item in response.json()["items"])

    assert emails() == ["admin@skillcortex.in", "arjun@example.com", "dhanushya@example.com"]
    assert emails(role="USER") == ["arjun@example.com", "dhanushya@example.com"]
    assert emails(department_id=str(cse.id)) == ["dhanushya@example.com"]
    assert emails(is_active="false") == ["arjun@example.com"]
    assert emails(q="DHANU") == ["dhanushya@example.com"]
    assert emails(q="98765") == ["admin@skillcortex.in", "arjun@example.com", "dhanushya@example.com"]  # phone
    assert len(client.get("/admin/users", params={"page_size": 2}, headers=headers).json()["items"]) == 2

    detail = client.get(f"/admin/users/{dhanushya.id}", headers=headers).json()
    assert detail["department"]["name"] == "CSE"
    assert (detail["bookings_count"], detail["confirmed_bookings_count"], detail["total_paid_paise"]) == (2, 1, 99_900)
    assert "password_hash" not in detail

    payments = client.get("/admin/payments", params={"user_id": str(dhanushya.id)}, headers=headers).json()
    assert payments["total"] == 1
    bookings = client.get("/admin/bookings", params={"user_id": str(dhanushya.id)}, headers=headers).json()
    assert bookings["total"] == 2


def test_deactivating_a_user_signs_them_out_everywhere(client: TestClient, db: Session, admin_headers: dict) -> None:
    learner = make_user(db, email="learner@example.com", password=DEFAULT_PASSWORD)
    login = client.post("/auth/login", json={"email": "learner@example.com", "password": DEFAULT_PASSWORD})
    refresh_token = login.cookies[REFRESH_COOKIE]
    access_token = login.json()["access_token"]

    response = client.put(f"/admin/users/{learner.id}", json={"is_active": False}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 401
    client.cookies.clear()
    refresh = client.post("/auth/refresh", headers={"Cookie": f"{REFRESH_COOKIE}={refresh_token}"})
    assert refresh.status_code == 401
    assert db.scalars(select(RefreshToken).where(RefreshToken.user_id == learner.id, RefreshToken.revoked_at.is_(None))).all() == []
    assert client.post("/auth/login", json={"email": "learner@example.com", "password": DEFAULT_PASSWORD}).status_code == 403

    reactivated = client.put(f"/admin/users/{learner.id}", json={"is_active": True}, headers=admin_headers)
    assert reactivated.json()["is_active"] is True
    assert client.post("/auth/login", json={"email": "learner@example.com", "password": DEFAULT_PASSWORD}).status_code == 200


def test_admin_cannot_deactivate_themselves(client: TestClient, db: Session) -> None:
    admin = make_user(db, role=UserRole.ADMIN)
    token, _ = create_access_token(admin.id, admin.role)

    response = client.put(f"/admin/users/{admin.id}", json={"is_active": False}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 409
    assert response.json()["detail"] == "You can't deactivate your own account."


def test_user_management_requires_admin_and_existing_users(
    client: TestClient, admin_headers: dict, learner_headers: dict
) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert client.get("/admin/users", headers=learner_headers).status_code == 403
    assert client.get(f"/admin/users/{missing}", headers=admin_headers).status_code == 404
    assert client.put(f"/admin/users/{missing}", json={"is_active": False}, headers=admin_headers).status_code == 404
