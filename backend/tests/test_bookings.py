from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BookingStatus, PaymentStatus, RecordStatus, SlotStatus, UserRole
from tests.factories import auth_header, make_booking, make_payment, make_slot, make_user, make_webinar


def book(client: TestClient, headers: dict, slot_id) -> "object":
    return client.post("/bookings", json={"slot_id": str(slot_id)}, headers=headers)


# --- creating bookings ----------------------------------------------------------


def test_booking_holds_a_seat_and_snapshots_the_price(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    webinar = make_webinar(db, price_paise=99_900)
    slot = make_slot(db, webinar, capacity=10)

    response = book(client, auth_header(learner), slot.id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["payment_status"] is None
    assert body["amount_paise"] == 99_900
    assert body["reference"].startswith("SC-")
    assert body["webinar"]["title"] == "Python Programming"
    assert body["slot"]["id"] == str(slot.id)
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=14) < expires_at - datetime.now(UTC) <= timedelta(minutes=15)
    db.refresh(slot)
    assert slot.available_seats == 9

    webinar.price_paise = 149_900  # later price change doesn't affect the booking
    db.flush()
    assert client.get(f"/bookings/{body['id']}", headers=auth_header(learner)).json()["amount_paise"] == 99_900


def test_guests_and_admins_cannot_book(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_webinar(db))
    admin = make_user(db, role=UserRole.ADMIN)

    assert client.post("/bookings", json={"slot_id": str(slot.id)}).status_code == 401
    response = book(client, auth_header(admin), slot.id)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only learner accounts can book webinars."


def test_full_slot_is_rejected(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_webinar(db), capacity=2, available_seats=0)

    response = book(client, auth_header(make_user(db)), slot.id)

    assert response.status_code == 409
    assert response.json()["detail"] == "This slot is full. Please choose another available slot."


def test_unbookable_slots_and_webinars(client: TestClient, db: Session) -> None:
    headers = auth_header(make_user(db))
    webinar = make_webinar(db)
    started = make_slot(db, webinar, starts_in=timedelta(minutes=-10))
    inactive = make_slot(db, webinar, status=SlotStatus.INACTIVE)
    retired_webinar_slot = make_slot(db, make_webinar(db, title="Retired", status=RecordStatus.INACTIVE))

    for slot in (started, inactive):
        response = book(client, headers, slot.id)
        assert response.status_code == 409
        assert response.json()["detail"] == "This slot is no longer available. Please choose another slot."
    retired = book(client, headers, retired_webinar_slot.id)
    assert (retired.status_code, retired.json()["detail"]) == (404, "This webinar is currently unavailable.")
    assert book(client, headers, "00000000-0000-0000-0000-000000000000").status_code == 404


def test_rebooking_returns_the_existing_hold_without_taking_another_seat(client: TestClient, db: Session) -> None:
    headers = auth_header(make_user(db))
    slot = make_slot(db, make_webinar(db), capacity=10)

    first = book(client, headers, slot.id)
    second = book(client, headers, slot.id)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    db.refresh(slot)
    assert slot.available_seats == 9


def test_cannot_book_a_slot_already_confirmed(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    slot = make_slot(db, make_webinar(db))
    make_booking(db, learner, slot, BookingStatus.CONFIRMED)

    response = book(client, auth_header(learner), slot.id)

    assert response.status_code == 409
    assert response.json()["detail"] == "You already have a confirmed booking for this slot."


def test_expired_hold_is_released_immediately_for_the_next_learner(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_webinar(db), capacity=1, available_seats=0)
    stale = make_booking(db, make_user(db), slot, expires_in=timedelta(minutes=-1))  # holds the only seat

    response = book(client, auth_header(make_user(db)), slot.id)

    assert response.status_code == 201
    db.refresh(stale)
    db.refresh(slot)
    assert stale.status == BookingStatus.EXPIRED
    assert slot.available_seats == 0  # released by the stale hold, taken by the new one


def test_own_expired_hold_is_replaced_by_a_new_booking(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    slot = make_slot(db, make_webinar(db), capacity=3, available_seats=2)
    stale = make_booking(db, learner, slot, expires_in=timedelta(minutes=-1))

    response = book(client, auth_header(learner), slot.id)

    assert response.status_code == 201
    assert response.json()["id"] != str(stale.id)
    db.refresh(stale)
    db.refresh(slot)
    assert stale.status == BookingStatus.EXPIRED
    assert slot.available_seats == 2  # one released, one taken


def test_free_webinar_is_confirmed_immediately(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_webinar(db, price_paise=0))

    body = book(client, auth_header(make_user(db)), slot.id).json()

    assert body["status"] == "CONFIRMED"
    assert body["expires_at"] is None
    assert body["confirmed_at"] is not None


# --- cancelling -----------------------------------------------------------------


def test_learner_cancels_unpaid_booking_and_seat_is_released(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    headers = auth_header(learner)
    slot = make_slot(db, make_webinar(db), capacity=5)
    booking_id = book(client, headers, slot.id).json()["id"]
    booking = next(b for b in learner.bookings if str(b.id) == booking_id)
    payment = make_payment(db, booking)

    response = client.post(f"/bookings/{booking_id}/cancel", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancelled_at"] is not None
    db.refresh(slot)
    db.refresh(payment)
    assert slot.available_seats == 5
    assert payment.status == PaymentStatus.FAILED
    assert client.post(f"/bookings/{booking_id}/cancel", headers=headers).status_code == 409


def test_paid_booking_cannot_be_cancelled_by_learner(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    booking = make_booking(db, learner, make_slot(db, make_webinar(db)), BookingStatus.CONFIRMED)

    response = client.post(f"/bookings/{booking.id}/cancel", headers=auth_header(learner))

    assert response.status_code == 409
    assert "contact support" in response.json()["detail"]


def test_learners_cannot_see_or_cancel_others_bookings(client: TestClient, db: Session) -> None:
    owner, other = make_user(db), make_user(db)
    booking = make_booking(db, owner, make_slot(db, make_webinar(db)))
    headers = auth_header(other)

    assert client.get(f"/bookings/{booking.id}", headers=headers).status_code == 404
    assert client.post(f"/bookings/{booking.id}/cancel", headers=headers).status_code == 404
    assert client.get("/bookings", headers=headers).json()["total"] == 0


# --- my bookings ----------------------------------------------------------------


def test_my_bookings_split_into_upcoming_and_past(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    webinar = make_webinar(db)

    def slot(days: float):
        return make_slot(db, webinar, starts_in=timedelta(days=days))

    confirmed_soon = make_booking(db, learner, slot(2), BookingStatus.CONFIRMED)
    make_payment(db, confirmed_soon, PaymentStatus.PAID)
    held_later = make_booking(db, learner, slot(5))
    expired_hold = make_booking(db, learner, slot(3), expires_in=timedelta(minutes=-5))
    cancelled = make_booking(db, learner, slot(4), BookingStatus.CANCELLED)
    attended = make_booking(db, learner, slot(-10), BookingStatus.COMPLETED)
    make_booking(db, make_user(db), slot(1), BookingStatus.CONFIRMED)  # someone else's

    def ids(scope: str) -> list[str]:
        body = client.get("/bookings", params={"scope": scope}, headers=auth_header(learner)).json()
        return [item["id"] for item in body["items"]]

    assert ids("upcoming") == [str(confirmed_soon.id), str(held_later.id)]
    assert ids("past") == [str(cancelled.id), str(expired_hold.id), str(attended.id)]  # latest session first
    everything = client.get("/bookings", headers=auth_header(learner)).json()
    assert everything["total"] == 5
    paid = next(item for item in everything["items"] if item["id"] == str(confirmed_soon.id))
    assert paid["payment_status"] == "PAID"


# --- admin ----------------------------------------------------------------------


def test_admin_lists_filters_and_views_bookings(
    client: TestClient, db: Session, admin_headers: dict, learner_headers: dict
) -> None:
    dhanushya = make_user(db, email="dhanushya@example.com")
    arjun = make_user(db, email="arjun@example.com")
    python, sql = make_webinar(db, title="Python"), make_webinar(db, title="SQL")
    python_booking = make_booking(db, dhanushya, make_slot(db, python), BookingStatus.CONFIRMED)
    make_booking(db, arjun, make_slot(db, sql))
    db.refresh(python_booking)

    def total(**params) -> int:
        response = client.get("/admin/bookings", params=params, headers=admin_headers)
        assert response.status_code == 200
        return response.json()["total"]

    assert total() == 2
    assert total(status="CONFIRMED") == 1
    assert total(webinar_id=str(sql.id)) == 1
    assert total(q="DHANUSHYA") == 1
    assert total(q=python_booking.reference) == 1
    assert total(user_id=str(arjun.id)) == 1

    detail = client.get(f"/admin/bookings/{python_booking.id}", headers=admin_headers).json()
    assert detail["user"]["email"] == "dhanushya@example.com"
    assert detail["webinar"]["title"] == "Python"
    assert client.get("/admin/bookings", headers=learner_headers).status_code == 403
