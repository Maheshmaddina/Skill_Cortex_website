from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationType,
    Payment,
    PaymentMethod,
    PaymentStatus,
    User,
)
from app.services.bookings import expire_stale_bookings
from tests.factories import auth_header, make_slot, make_user, make_webinar
from tests.fakes import FakeNotifier

UTR = "412345678901"


@pytest.fixture(autouse=True)
def upi_enabled(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "upi_id", "skillcortex@okaxis")
    monkeypatch.setattr(get_settings(), "upi_payee_name", "Skill Cortex AI")


def hold_seat(client: TestClient, db: Session, user: User, capacity: int = 5) -> Booking:
    slot = make_slot(db, make_webinar(db), capacity)
    response = client.post("/bookings", json={"slot_id": str(slot.id)}, headers=auth_header(user))
    assert response.status_code == 201
    return db.get(Booking, response.json()["id"])


def pay_by_upi(client: TestClient, user: User, booking: Booking, utr: str = UTR):
    return client.post("/payments/upi", json={"booking_id": str(booking.id), "utr": utr}, headers=auth_header(user))


def test_learner_gets_upi_id_and_qr_link_for_their_booking(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)

    response = client.get("/payments/upi", params={"booking_id": str(booking.id)}, headers=auth_header(learner))

    assert response.status_code == 200
    details = response.json()
    assert details["upi_id"] == "skillcortex@okaxis"
    assert details["amount_paise"] == 99_900
    uri = urlparse(details["upi_uri"])
    assert (uri.scheme, uri.netloc) == ("upi", "pay")
    assert parse_qs(uri.query) == {
        "pa": ["skillcortex@okaxis"],
        "pn": ["Skill Cortex AI"],
        "am": ["999.00"],
        "cu": ["INR"],
        "tn": [f"Skill Cortex {booking.reference}"],
    }
    other = make_user(db)
    assert client.get("/payments/upi", params={"booking_id": str(booking.id)}, headers=auth_header(other)).status_code == 404


def test_upi_is_hidden_until_a_upi_id_is_configured(client: TestClient, db: Session, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "upi_id", "")
    learner = make_user(db)
    booking = hold_seat(client, db, learner)

    assert client.get("/payments/upi", params={"booking_id": str(booking.id)}, headers=auth_header(learner)).status_code == 503
    assert pay_by_upi(client, learner, booking).status_code == 503


def test_submitting_a_utr_keeps_the_seat_until_an_admin_verifies(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)

    response = pay_by_upi(client, learner, booking, utr="4123 4567 8901")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["payment_status"] == "PENDING"
    assert body["upi_payment"]["upi_reference"] == UTR
    assert body["upi_payment"]["status"] == "PENDING"
    db.refresh(booking)
    assert booking.expires_at == booking.slot.start_at  # not released after 15 minutes
    assert expire_stale_bookings(db, datetime.now(UTC) + timedelta(hours=1)) == 0

    # Same UTR again is fine; a different one, card checkout or cancelling is not.
    assert pay_by_upi(client, learner, booking).status_code == 200
    assert pay_by_upi(client, learner, booking, utr="999999999999").status_code == 409
    assert client.post("/payments/create-order", json={"booking_id": str(booking.id)}, headers=auth_header(learner)).status_code == 409
    cancel = client.post(f"/bookings/{booking.id}/cancel", headers=auth_header(learner))
    assert cancel.status_code == 409
    assert "being verified" in cancel.json()["detail"]


@pytest.mark.parametrize("utr", ["12345", "41234567890a", "4123456789012"])
def test_utr_must_be_12_digits(client: TestClient, db: Session, utr: str) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)
    response = pay_by_upi(client, learner, booking, utr=utr)
    assert response.status_code == 400
    assert "12-digit" in response.json()["detail"]


def test_a_utr_cannot_be_reused_for_another_booking(client: TestClient, db: Session) -> None:
    first, second = make_user(db), make_user(db)
    pay_by_upi(client, first, hold_seat(client, db, first))

    response = pay_by_upi(client, second, hold_seat(client, db, second))

    assert response.status_code == 409
    assert "already been submitted" in response.json()["detail"]


def test_admin_confirms_the_upi_payment(
    client: TestClient, db: Session, admin_headers: dict, notifier: FakeNotifier
) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)
    pay_by_upi(client, learner, booking)

    to_verify = client.get("/admin/payments", params={"method": "UPI", "status": "PENDING"}, headers=admin_headers).json()
    assert to_verify["total"] == 1
    [payment] = to_verify["items"]
    assert (payment["method"], payment["upi_reference"], payment["razorpay_order_id"]) == ("UPI", UTR, None)
    assert client.get("/admin/dashboard/stats", headers=admin_headers).json()["payments"]["upi_awaiting_verification"] == 1
    assert client.get("/admin/payments", params={"q": UTR[-6:]}, headers=admin_headers).json()["total"] == 1

    response = client.post(f"/admin/payments/{payment['id']}/confirm-upi", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"
    assert response.json()["booking"]["status"] == "CONFIRMED"
    db.refresh(booking)
    assert (booking.status, booking.expires_at) == (BookingStatus.CONFIRMED, None)
    receipt = client.get(f"/bookings/{booking.id}", headers=auth_header(learner)).json()["paid_payment"]
    assert (receipt["method"], receipt["upi_reference"], receipt["amount_paise"]) == ("UPI", UTR, 99_900)
    assert receipt["paid_at"] is not None
    assert notifier.dispatch_calls == 1
    confirmations = db.scalars(
        select(Notification).where(
            Notification.booking_id == booking.id, Notification.type == NotificationType.BOOKING_CONFIRMATION
        )
    ).all()
    assert {n.recipient_address for n in confirmations} == {learner.email, learner.phone}
    # Can't be confirmed twice.
    assert client.post(f"/admin/payments/{payment['id']}/confirm-upi", headers=admin_headers).status_code == 409
    assert client.get("/admin/dashboard/stats", headers=admin_headers).json()["payments"]["upi_awaiting_verification"] == 0


def test_admin_rejects_and_the_learner_can_try_again(client: TestClient, db: Session, admin_headers: dict) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)
    pay_by_upi(client, learner, booking)
    payment = db.scalars(select(Payment).where(Payment.booking_id == booking.id)).one()

    response = client.post(
        f"/admin/payments/{payment.id}/reject-upi", json={"reason": "No payment with this UTR"}, headers=admin_headers
    )

    assert response.json()["status"] == "FAILED"
    mine = client.get(f"/bookings/{booking.id}", headers=auth_header(learner)).json()
    assert mine["status"] == "PENDING"
    assert mine["upi_payment"] == {
        "upi_reference": UTR,
        "status": "FAILED",
        "failure_reason": "No payment with this UTR",
        "created_at": mine["upi_payment"]["created_at"],
    }
    db.refresh(booking)
    assert timedelta(minutes=29) < booking.expires_at - datetime.now(UTC) <= timedelta(minutes=30)

    retry = pay_by_upi(client, learner, booking, utr="512345678901")
    assert retry.status_code == 200
    assert retry.json()["upi_payment"]["status"] == "PENDING"


def test_a_utr_sent_just_after_the_hold_expired_takes_the_seat_back(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner, capacity=1)
    expire_stale_bookings(db, datetime.now(UTC) + timedelta(minutes=16))
    db.refresh(booking)
    assert booking.status == BookingStatus.EXPIRED

    response = pay_by_upi(client, learner, booking)

    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    db.refresh(booking.slot)
    assert booking.slot.available_seats == 0


def test_a_late_utr_for_a_full_session_is_refused_with_refund_guidance(client: TestClient, db: Session) -> None:
    learner, other = make_user(db), make_user(db)
    booking = hold_seat(client, db, learner, capacity=1)
    expire_stale_bookings(db, datetime.now(UTC) + timedelta(minutes=16))
    client.post("/bookings", json={"slot_id": str(booking.slot_id)}, headers=auth_header(other))

    response = pay_by_upi(client, learner, booking)

    assert response.status_code == 409
    assert "refund" in response.json()["detail"]


def test_cancelling_a_confirmed_upi_booking_marks_a_manual_refund(
    client: TestClient, db: Session, admin_headers: dict, razorpay
) -> None:
    learner = make_user(db)
    booking = hold_seat(client, db, learner)
    pay_by_upi(client, learner, booking)
    payment = db.scalars(select(Payment).where(Payment.booking_id == booking.id)).one()
    client.post(f"/admin/payments/{payment.id}/confirm-upi", headers=admin_headers)

    response = client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers)

    assert response.status_code == 200
    db.refresh(payment)
    assert payment.method == PaymentMethod.UPI
    assert payment.status == PaymentStatus.REFUNDED
    assert f"manually via UPI (UTR {UTR})" in payment.failure_reason
    assert razorpay.refunds == []  # nothing sent to Razorpay
