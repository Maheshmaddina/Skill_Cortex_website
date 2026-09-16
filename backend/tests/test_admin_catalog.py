from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BookingStatus, RecordStatus
from tests.factories import make_booking, make_department, make_slot, make_user, make_webinar


def at(days: float, hours: float = 0) -> str:
    return (datetime.now(UTC) + timedelta(days=days, hours=hours)).isoformat()


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/admin/departments"),
        ("POST", "/admin/departments"),
        ("GET", "/admin/webinars"),
        ("POST", "/admin/webinars"),
        ("PUT", "/admin/webinars/00000000-0000-0000-0000-000000000000"),
        ("POST", "/admin/slots"),
        ("DELETE", "/admin/slots/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_catalog_management_requires_admin(
    client: TestClient, learner_headers: dict, method: str, path: str
) -> None:
    assert client.request(method, path, json={}).status_code == 401
    assert client.request(method, path, json={}, headers=learner_headers).status_code == 403


# --- departments ----------------------------------------------------------------


def test_admin_creates_updates_and_deactivates_department(client: TestClient, admin_headers: dict) -> None:
    created = client.post(
        "/admin/departments", json={"name": "  Cyber Security ", "description": "Security"}, headers=admin_headers
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Cyber Security"
    assert created.json()["status"] == "ACTIVE"
    department_id = created.json()["id"]

    duplicate = client.post("/admin/departments", json={"name": "cyber security"}, headers=admin_headers)
    assert duplicate.status_code == 409

    updated = client.put(
        f"/admin/departments/{department_id}", json={"description": "Offensive and defensive"}, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json() | {"description": "Offensive and defensive", "name": "Cyber Security"} == updated.json()

    assert client.put(f"/admin/departments/{department_id}", json={"name": None}, headers=admin_headers).status_code == 422

    deactivated = client.delete(f"/admin/departments/{department_id}", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"
    assert "Cyber Security" not in [d["name"] for d in client.get("/departments").json()]
    assert department_id in [d["id"] for d in client.get("/admin/departments", headers=admin_headers).json()]


def test_department_rename_cannot_collide(client: TestClient, db: Session, admin_headers: dict) -> None:
    make_department(db, "Data Science")
    other = make_department(db, "Analytics")

    response = client.put(f"/admin/departments/{other.id}", json={"name": "DATA SCIENCE"}, headers=admin_headers)

    assert response.status_code == 409
    assert client.get("/admin/departments/00000000-0000-0000-0000-000000000000", headers=admin_headers).status_code == 404


# --- webinars -------------------------------------------------------------------


def webinar_payload(department_ids: list, **overrides) -> dict:
    payload = {
        "title": "Python Programming",
        "description": "Learn Python fundamentals and practical programming.",
        "instructor": "A. Kumar",
        "price_paise": 99_900,
        "duration_minutes": 60,
        "department_ids": [str(i) for i in department_ids],
    }
    return payload | overrides


def test_admin_creates_webinar_for_multiple_departments(client: TestClient, db: Session, admin_headers: dict) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")

    response = client.post("/admin/webinars", json=webinar_payload([cse.id, data_science.id]), headers=admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert {d["name"] for d in body["departments"]} == {"CSE", "Data Science"}
    assert body["price_paise"] == 99_900
    assert body["status"] == "ACTIVE"


@pytest.mark.parametrize(
    "overrides",
    [{"department_ids": []}, {"price_paise": -1}, {"duration_minutes": 0}, {"title": "  "}, {"description": "short"}],
)
def test_webinar_input_is_validated(client: TestClient, db: Session, admin_headers: dict, overrides: dict) -> None:
    department = make_department(db)

    response = client.post("/admin/webinars", json=webinar_payload([department.id]) | overrides, headers=admin_headers)

    assert response.status_code == 422


def test_webinar_departments_must_be_active(client: TestClient, db: Session, admin_headers: dict) -> None:
    inactive = make_department(db, status=RecordStatus.INACTIVE)

    response = client.post("/admin/webinars", json=webinar_payload([inactive.id]), headers=admin_headers)

    assert response.status_code == 400
    assert str(inactive.id) in response.json()["detail"]


def test_admin_updates_webinar_departments_price_and_clears_instructor(
    client: TestClient, db: Session, admin_headers: dict
) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")
    webinar = make_webinar(db, [cse])

    response = client.put(
        f"/admin/webinars/{webinar.id}",
        json={"department_ids": [str(data_science.id)], "instructor": None, "price_paise": 149_900},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert [d["name"] for d in body["departments"]] == ["Data Science"]
    assert body["instructor"] is None
    assert body["price_paise"] == 149_900
    assert body["title"] == "Python Programming"


def test_deactivated_webinar_leaves_public_catalog(client: TestClient, db: Session, admin_headers: dict) -> None:
    webinar = make_webinar(db)

    response = client.delete(f"/admin/webinars/{webinar.id}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "INACTIVE"
    public = client.get(f"/webinars/{webinar.id}")
    assert public.status_code == 404
    assert public.json()["detail"] == "This webinar is currently unavailable."
    assert client.get(f"/admin/webinars/{webinar.id}", headers=admin_headers).status_code == 200


def test_admin_webinar_list_filters_and_paginates(client: TestClient, db: Session, admin_headers: dict) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")
    make_webinar(db, [cse], title="Python Basics")
    make_webinar(db, [data_science], title="SQL for Analysts")
    make_webinar(db, [cse], title="Advanced Python", status=RecordStatus.INACTIVE)

    def titles(**params) -> tuple[set[str], int]:
        body = client.get("/admin/webinars", params=params, headers=admin_headers).json()
        return {w["title"] for w in body["items"]}, body["total"]

    assert titles() == ({"Python Basics", "SQL for Analysts", "Advanced Python"}, 3)
    assert titles(status="ACTIVE")[1] == 2
    assert titles(department_id=str(cse.id)) == ({"Python Basics", "Advanced Python"}, 2)
    assert titles(q="python")[1] == 2
    assert titles(page=2, page_size=2) == ({"SQL for Analysts"}, 3)  # ordered by title


# --- slots ----------------------------------------------------------------------


def test_admin_creates_slot_with_all_seats_available(client: TestClient, db: Session, admin_headers: dict) -> None:
    webinar = make_webinar(db)

    response = client.post(
        "/admin/slots",
        json={"webinar_id": str(webinar.id), "start_at": at(7), "end_at": at(7, hours=1), "capacity": 25},
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["capacity"], body["available_seats"], body["booked_seats"], body["is_full"]) == (25, 25, 0, False)


@pytest.mark.parametrize(
    "overrides, status_code, detail",
    [
        ({"start_at": at(-1), "end_at": at(-1, hours=1)}, 400, "Slot must start in the future."),
        ({"end_at": at(6)}, 400, "End time must be after start time."),
        ({"start_at": "2030-01-01T10:00:00"}, 422, None),  # timezone required
        ({"capacity": 0}, 422, None),
    ],
)
def test_slot_input_is_validated(
    client: TestClient, db: Session, admin_headers: dict, overrides: dict, status_code: int, detail: str | None
) -> None:
    webinar = make_webinar(db)
    payload = {"webinar_id": str(webinar.id), "start_at": at(7), "end_at": at(7, hours=1), "capacity": 10}

    response = client.post("/admin/slots", json=payload | overrides, headers=admin_headers)

    assert response.status_code == status_code
    if detail:
        assert response.json()["detail"] == detail


def test_slot_for_unknown_webinar_is_rejected(client: TestClient, admin_headers: dict) -> None:
    payload = {
        "webinar_id": "00000000-0000-0000-0000-000000000000",
        "start_at": at(7),
        "end_at": at(7, hours=1),
        "capacity": 10,
    }

    assert client.post("/admin/slots", json=payload, headers=admin_headers).status_code == 404


def test_capacity_cannot_drop_below_booked_seats(client: TestClient, db: Session, admin_headers: dict) -> None:
    slot = make_slot(db, make_webinar(db), capacity=10, available_seats=7)  # 3 seats taken

    too_low = client.put(f"/admin/slots/{slot.id}", json={"capacity": 2}, headers=admin_headers)
    assert too_low.status_code == 409
    assert "3 seats" in too_low.json()["detail"]

    reduced = client.put(f"/admin/slots/{slot.id}", json={"capacity": 5}, headers=admin_headers)
    assert reduced.status_code == 200
    assert (reduced.json()["capacity"], reduced.json()["available_seats"], reduced.json()["booked_seats"]) == (5, 2, 3)


def test_slot_with_live_bookings_cannot_be_rescheduled_or_deactivated(
    client: TestClient, db: Session, admin_headers: dict
) -> None:
    slot = make_slot(db, make_webinar(db), available_seats=9)
    booking = make_booking(db, make_user(db), slot)
    new_times = {"start_at": at(8), "end_at": at(8, hours=1)}

    assert client.put(f"/admin/slots/{slot.id}", json=new_times, headers=admin_headers).status_code == 409
    assert client.delete(f"/admin/slots/{slot.id}", headers=admin_headers).status_code == 409
    # Capacity changes are still fine.
    assert client.put(f"/admin/slots/{slot.id}", json={"capacity": 20}, headers=admin_headers).status_code == 200

    booking.status = BookingStatus.EXPIRED
    db.flush()

    assert client.put(f"/admin/slots/{slot.id}", json=new_times, headers=admin_headers).status_code == 200
    deactivated = client.delete(f"/admin/slots/{slot.id}", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"


def test_admin_slot_list_defaults_to_upcoming(client: TestClient, db: Session, admin_headers: dict) -> None:
    webinar = make_webinar(db)
    make_slot(db, webinar, starts_in=timedelta(days=2))
    make_slot(db, webinar, starts_in=timedelta(days=-2))

    upcoming = client.get("/admin/slots", params={"webinar_id": str(webinar.id)}, headers=admin_headers).json()
    everything = client.get(
        "/admin/slots", params={"webinar_id": str(webinar.id), "upcoming": "false"}, headers=admin_headers
    ).json()

    assert upcoming["total"] == 1
    assert everything["total"] == 2
