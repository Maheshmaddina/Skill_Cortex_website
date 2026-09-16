import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Payment, PaymentEvent, PaymentStatus, User
from app.services.bookings import expire_stale_bookings
from tests.factories import auth_header, make_booking, make_slot, make_user, make_webinar
from tests.fakes import FakeRazorpay, sign_checkout, sign_webhook, webhook_body


@pytest.fixture
def learner(db: Session) -> User:
    return make_user(db, email="learner@example.com")


@pytest.fixture
def booking(db: Session, learner: User) -> Booking:
    slot = make_slot(db, make_webinar(db), capacity=5, available_seats=4)  # this booking holds one seat
    return make_booking(db, learner, slot)


def create_order(client: TestClient, user: User, booking: Booking):
    return client.post("/payments/create-order", json={"booking_id": str(booking.id)}, headers=auth_header(user))


def verify(client: TestClient, user: User, order_id: str, payment_id: str = "pay_CHECKOUT01", signature: str | None = None):
    payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature or sign_checkout(order_id, payment_id),
    }
    return client.post("/payments/verify", json=payload, headers=auth_header(user))


def post_webhook(client: TestClient, body: bytes, *, event_id: str | None = None, signature: str | None = None):
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature or sign_webhook(body),
        "X-Razorpay-Event-Id": event_id or f"evt_{uuid.uuid4().hex[:14]}",
    }
    return client.post("/payments/webhook", content=body, headers=headers)


def payment_for(db: Session, order_id: str) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.razorpay_order_id == order_id))
    db.refresh(payment)
    return payment


# --- create order ---------------------------------------------------------------


def test_create_order_returns_checkout_options_and_reuses_the_order(
    client: TestClient, db: Session, razorpay: FakeRazorpay, learner: User, booking: Booking
) -> None:
    first = create_order(client, learner, booking)

    assert first.status_code == 200
    body = first.json()
    assert body["key_id"] == "rzp_test_dummykey"
    assert body["order_id"] == razorpay.orders[0]["id"]
    assert (body["amount_paise"], body["currency"]) == (99_900, "INR")
    assert body["booking_reference"] == booking.reference
    assert body["webinar_title"] == "Python Programming"
    assert body["prefill"] == {"name": "Test User", "email": "learner@example.com", "contact": "9876543210"}
    assert razorpay.orders[0]["receipt"] == booking.reference
    assert razorpay.orders[0]["amount"] == 99_900
    assert payment_for(db, body["order_id"]).status == PaymentStatus.PENDING

    second = create_order(client, learner, booking)
    assert second.json()["order_id"] == body["order_id"]
    assert len(razorpay.orders) == 1


def test_create_order_rejects_unpayable_bookings(
    client: TestClient, db: Session, razorpay: FakeRazorpay, learner: User
) -> None:
    confirmed = make_booking(db, learner, make_slot(db, make_webinar(db)), BookingStatus.CONFIRMED)
    expired = make_booking(db, learner, make_slot(db, make_webinar(db)), expires_in=timedelta(minutes=-1))
    someone_elses = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))

    assert create_order(client, learner, confirmed).json()["detail"] == "This booking is already paid."
    expired_response = create_order(client, learner, expired)
    assert expired_response.status_code == 409
    assert expired_response.json()["detail"] == "This booking has expired. Please book the slot again."
    assert create_order(client, learner, someone_elses).status_code == 404
    assert razorpay.orders == []


# --- checkout verification ------------------------------------------------------


def test_verified_checkout_confirms_the_booking(
    client: TestClient, db: Session, learner: User, booking: Booking
) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]

    response = verify(client, learner, order_id)

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "confirmed"
    assert body["message"] == "Payment successful. Your booking is confirmed."
    assert body["booking"]["status"] == "CONFIRMED"
    assert body["booking"]["payment_status"] == "PAID"
    assert body["booking"]["expires_at"] is None
    payment = payment_for(db, order_id)
    assert payment.razorpay_payment_id == "pay_CHECKOUT01"
    assert payment.razorpay_signature == sign_checkout(order_id, "pay_CHECKOUT01")
    assert payment.paid_at is not None
    db.refresh(booking.slot)
    assert booking.slot.available_seats == 4  # the held seat is kept, not taken again

    again = verify(client, learner, order_id)
    assert (again.status_code, again.json()["outcome"]) == (200, "already_confirmed")


def test_tampered_signature_does_not_confirm(client: TestClient, db: Session, learner: User, booking: Booking) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]

    response = verify(client, learner, order_id, signature="0" * 64)

    assert response.status_code == 400
    assert payment_for(db, order_id).status == PaymentStatus.PENDING
    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING


def test_cannot_verify_someone_elses_order(client: TestClient, db: Session, learner: User, booking: Booking) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]

    assert verify(client, make_user(db), order_id).status_code == 404


# --- webhooks -------------------------------------------------------------------


def test_webhook_confirms_when_the_browser_never_returned(
    client: TestClient, db: Session, learner: User, booking: Booking
) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]
    body = webhook_body("payment.captured", order_id=order_id)

    response = post_webhook(client, body, event_id="evt_same")
    replay = post_webhook(client, body, event_id="evt_same")

    assert response.json() == {"status": "confirmed"}
    assert replay.json() == {"status": "duplicate"}
    db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED
    event = db.scalar(select(PaymentEvent).where(PaymentEvent.razorpay_event_id == "evt_same"))
    assert event.processed_at is not None
    # A later Checkout verify for the same order is harmless.
    assert verify(client, learner, order_id, payment_id="pay_WEBHOOK01").json()["outcome"] == "already_confirmed"


def test_webhook_with_bad_signature_is_rejected(
    client: TestClient, db: Session, learner: User, booking: Booking
) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]

    response = post_webhook(client, webhook_body("payment.captured", order_id=order_id), signature="forged")

    assert response.status_code == 400
    assert payment_for(db, order_id).status == PaymentStatus.PENDING
    assert db.scalar(select(func.count()).select_from(PaymentEvent)) == 0


def test_webhook_for_unknown_orders_and_events_is_acknowledged(client: TestClient) -> None:
    unknown_order = post_webhook(client, webhook_body("payment.captured", order_id="order_NOTOURS"))
    other_event = post_webhook(client, b'{"event": "refund.processed", "payload": {}}')

    assert (unknown_order.status_code, unknown_order.json()) == (200, {"status": "ignored"})
    assert other_event.json() == {"status": "ignored"}


def test_webhook_amount_mismatch_does_not_confirm(
    client: TestClient, db: Session, learner: User, booking: Booking
) -> None:
    order_id = create_order(client, learner, booking).json()["order_id"]

    response = post_webhook(client, webhook_body("payment.captured", order_id=order_id, amount_paise=100))

    assert response.json() == {"status": "amount_mismatch"}
    payment = payment_for(db, order_id)
    assert payment.status == PaymentStatus.PENDING
    assert "Amount mismatch" in payment.failure_reason
    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING


def test_failed_attempt_allows_retry_with_a_new_order(
    client: TestClient, db: Session, razorpay: FakeRazorpay, learner: User, booking: Booking
) -> None:
    first_order = create_order(client, learner, booking).json()["order_id"]

    failed = post_webhook(
        client, webhook_body("payment.failed", order_id=first_order, error_description="Card declined by bank")
    )

    assert failed.json() == {"status": "failed"}
    first_payment = payment_for(db, first_order)
    assert (first_payment.status, first_payment.failure_reason) == (PaymentStatus.FAILED, "Card declined by bank")
    db.refresh(booking)
    assert booking.status == BookingStatus.PENDING  # seat still held for the retry

    second_order = create_order(client, learner, booking).json()["order_id"]
    assert second_order != first_order
    assert len(razorpay.orders) == 2
    assert verify(client, learner, second_order).json()["outcome"] == "confirmed"


def test_capture_on_an_earlier_order_supersedes_the_newer_open_order(
    client: TestClient, db: Session, learner: User, booking: Booking
) -> None:
    first_order = create_order(client, learner, booking).json()["order_id"]
    post_webhook(client, webhook_body("payment.failed", order_id=first_order))
    second_order = create_order(client, learner, booking).json()["order_id"]

    # The learner's retry inside the original Checkout succeeds after all.
    response = post_webhook(client, webhook_body("payment.captured", order_id=first_order))

    assert response.json() == {"status": "confirmed"}
    assert payment_for(db, first_order).status == PaymentStatus.PAID
    superseded = payment_for(db, second_order)
    assert superseded.status == PaymentStatus.FAILED
    assert superseded.failure_reason == "Superseded by another successful payment."


# --- payments that arrive after the hold expired (decision D4) ------------------


def test_late_payment_revives_the_booking_when_a_seat_is_free(
    client: TestClient, db: Session, learner: User
) -> None:
    slot = make_slot(db, make_webinar(db), capacity=2, available_seats=1)
    late = make_booking(db, learner, slot)
    order_id = create_order(client, learner, late).json()["order_id"]
    late.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    assert expire_stale_bookings(db) == 1

    response = post_webhook(client, webhook_body("payment.captured", order_id=order_id))

    assert response.json() == {"status": "confirmed"}
    db.refresh(late)
    db.refresh(slot)
    assert late.status == BookingStatus.CONFIRMED
    assert slot.available_seats == 1
    assert payment_for(db, order_id).status == PaymentStatus.PAID


def test_late_payment_is_refunded_when_the_slot_filled_up(
    client: TestClient, db: Session, razorpay: FakeRazorpay, learner: User
) -> None:
    slot = make_slot(db, make_webinar(db), capacity=1, available_seats=0)
    late = make_booking(db, learner, slot)
    order_id = create_order(client, learner, late).json()["order_id"]
    late.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    expire_stale_bookings(db)
    slot.available_seats = 0  # someone else took the released seat
    db.flush()

    response = post_webhook(client, webhook_body("payment.captured", order_id=order_id, payment_id="pay_LATE01"))

    assert response.json() == {"status": "refunded"}
    assert [(r["payment_id"], r["amount"]) for r in razorpay.refunds] == [("pay_LATE01", 99_900)]
    payment = payment_for(db, order_id)
    assert payment.status == PaymentStatus.REFUNDED
    assert payment.razorpay_refund_id == razorpay.refunds[0]["id"]
    db.refresh(late)
    assert late.status == BookingStatus.FAILED

    checkout = verify(client, learner, order_id, payment_id="pay_LATE01")
    assert checkout.json()["outcome"] == "refunded"
    assert "full refund" in checkout.json()["message"]
    assert len(razorpay.refunds) == 1  # not refunded twice


# --- admin ----------------------------------------------------------------------


def paid_booking(db: Session, user: User, slot) -> tuple[Booking, Payment]:
    booking = make_booking(db, user, slot, BookingStatus.CONFIRMED)
    payment = Payment(
        booking=booking,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:14]}",
        razorpay_payment_id=f"pay_{uuid.uuid4().hex[:14]}",
        amount_paise=booking.amount_paise,
        status=PaymentStatus.PAID,
        paid_at=datetime.now(UTC),
    )
    db.add(payment)
    db.flush()
    return booking, payment


def test_admin_cancels_a_paid_booking_with_a_full_refund(
    client: TestClient, db: Session, razorpay: FakeRazorpay, admin_headers: dict, learner: User
) -> None:
    slot = make_slot(db, make_webinar(db), capacity=5, available_seats=4)
    booking, payment = paid_booking(db, learner, slot)

    response = client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["payment_status"] == "REFUNDED"
    assert [(r["payment_id"], r["amount"]) for r in razorpay.refunds] == [(payment.razorpay_payment_id, 99_900)]
    db.refresh(slot)
    assert slot.available_seats == 5
    assert client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers).status_code == 409


def test_admin_cancels_a_pending_booking_without_refund(
    client: TestClient, db: Session, razorpay: FakeRazorpay, admin_headers: dict, learner: User, booking: Booking
) -> None:
    response = client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers)

    assert response.json()["status"] == "CANCELLED"
    assert razorpay.refunds == []
    db.refresh(booking.slot)
    assert booking.slot.available_seats == 5


def test_refund_failure_leaves_the_booking_confirmed(
    client: TestClient, db: Session, razorpay: FakeRazorpay, admin_headers: dict, learner: User
) -> None:
    booking, payment = paid_booking(db, learner, make_slot(db, make_webinar(db)))
    razorpay.fail_refunds = True

    response = client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers)

    assert response.status_code == 502
    db.refresh(booking)
    db.refresh(payment)
    assert (booking.status, payment.status) == (BookingStatus.CONFIRMED, PaymentStatus.PAID)


def test_admin_cancels_a_slot_and_refunds_everyone(
    client: TestClient, db: Session, razorpay: FakeRazorpay, admin_headers: dict
) -> None:
    webinar = make_webinar(db)
    slot = make_slot(db, webinar, capacity=5, available_seats=2)
    paid_booking(db, make_user(db), slot)
    paid_booking(db, make_user(db), slot)
    pending = make_booking(db, make_user(db), slot)

    response = client.post(f"/admin/slots/{slot.id}/cancel", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["cancelled_bookings"], body["refunds_issued"]) == (3, 2)
    assert (body["slot"]["status"], body["slot"]["available_seats"]) == ("CANCELLED", 5)
    assert len(razorpay.refunds) == 2
    db.refresh(pending)
    assert pending.status == BookingStatus.CANCELLED
    assert client.get(f"/webinars/{webinar.id}/slots").json() == []


def test_cancellations_require_admin(client: TestClient, db: Session, learner_headers: dict, booking: Booking) -> None:
    assert client.post(f"/admin/bookings/{booking.id}/cancel", headers=learner_headers).status_code == 403
    assert client.post(f"/admin/slots/{booking.slot_id}/cancel", headers=learner_headers).status_code == 403


def test_admin_payment_list_and_detail(client: TestClient, db: Session, admin_headers: dict) -> None:
    dhanushya = make_user(db, email="dhanushya@example.com")
    _, paid = paid_booking(db, dhanushya, make_slot(db, make_webinar(db, title="Python")))
    pending_booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db, title="SQL")))
    db.add(Payment(booking=pending_booking, razorpay_order_id="order_PENDING01", amount_paise=99_900))
    db.flush()

    def total(**params) -> int:
        return client.get("/admin/payments", params=params, headers=admin_headers).json()["total"]

    assert total() == 2
    assert total(status="PAID") == 1
    assert total(q="order_PENDING") == 1
    assert total(q="Dhanushya@") == 1
    assert total(booking_id=str(pending_booking.id)) == 1

    detail = client.get(f"/admin/payments/{paid.id}", headers=admin_headers).json()
    assert detail["razorpay_payment_id"] == paid.razorpay_payment_id
    assert detail["booking"]["user"]["email"] == "dhanushya@example.com"
    assert detail["booking"]["webinar"]["title"] == "Python"
