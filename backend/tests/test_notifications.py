from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RecipientType,
)
from app.services.bookings import expire_stale_bookings
from app.services.notification_providers import NotificationProviders
from app.services.notifications import (
    REDACTED_RESET_MESSAGE,
    deliver_password_reset,
    dispatch_pending,
    notify_booking_confirmed,
    record_password_reset,
)
from tests.factories import auth_header, make_booking, make_department, make_slot, make_user, make_webinar
from tests.fakes import FakeEmailProvider, FakeNotifier, FakeSmsProvider, webhook_body
from tests.test_payments import create_order, paid_booking, post_webhook, verify

EMAIL, SMS = NotificationChannel.EMAIL, NotificationChannel.SMS


def notifications(db: Session, **filters) -> list[Notification]:
    query = select(Notification)
    for field, value in filters.items():
        query = query.where(getattr(Notification, field) == value)
    return list(db.scalars(query.order_by(Notification.channel, Notification.recipient_address)))


@pytest.fixture
def providers() -> NotificationProviders:
    return NotificationProviders(email=FakeEmailProvider(), sms=FakeSmsProvider())


def queue_paid_confirmation(db: Session) -> Booking:
    booking, payment = paid_booking(db, make_user(db, email="learner@example.com"), make_slot(db, make_webinar(db)))
    notify_booking_confirmed(db, booking, payment)
    return booking


# --- what gets queued -----------------------------------------------------------


def test_registration_queues_a_welcome_email(client: TestClient, db: Session, notifier: FakeNotifier) -> None:
    department = make_department(db)
    payload = {
        "name": "Dhanushya",
        "email": "dhanushya@example.com",
        "phone": "9876543210",
        "password": "Secret123",
        "department_id": str(department.id),
    }

    assert client.post("/auth/register", json=payload).status_code == 201

    [welcome] = notifications(db, type=NotificationType.REGISTRATION)
    assert (welcome.channel, welcome.recipient_address, welcome.status) == (EMAIL, "dhanushya@example.com", NotificationStatus.PENDING)
    assert welcome.subject == "Welcome to Skill Cortex"
    assert notifier.dispatch_calls == 1


def test_verified_payment_notifies_learner_and_admins_exactly_once(
    client: TestClient, db: Session, notifier: FakeNotifier
) -> None:
    learner = make_user(db, email="learner@example.com")
    booking = make_booking(db, learner, make_slot(db, make_webinar(db), capacity=5, available_seats=4))
    order_id = create_order(client, learner, booking).json()["order_id"]

    assert verify(client, learner, order_id).json()["outcome"] == "confirmed"
    post_webhook(client, webhook_body("payment.captured", order_id=order_id, payment_id="pay_CHECKOUT01"))

    learner_rows = notifications(db, type=NotificationType.BOOKING_CONFIRMATION)
    assert [(n.channel, n.recipient_address, n.recipient_type) for n in learner_rows] == [
        (EMAIL, "learner@example.com", RecipientType.USER),
        (SMS, "9876543210", RecipientType.USER),
    ]
    admin_rows = notifications(db, type=NotificationType.ADMIN_PAYMENT)
    assert [(n.channel, n.recipient_address) for n in admin_rows] == [
        (EMAIL, "ops@skillcortex.in"),
        (EMAIL, "owner@skillcortex.in"),
        (SMS, "9000000001"),
    ]
    db.refresh(booking)
    email = learner_rows[0]
    for expected in (booking.reference, "Python Programming", "₹999", "pay_CHECKOUT01"):
        assert expected in email.message
    assert learner_rows[1].payload["booking_id"] == booking.reference
    assert "learner@example.com" in admin_rows[0].message  # admin sees contact details
    assert notifier.dispatch_calls == 2  # once per request; the replay added no rows


def test_free_booking_confirmation_goes_to_the_learner_only(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    slot = make_slot(db, make_webinar(db, price_paise=0))

    assert client.post("/bookings", json={"slot_id": str(slot.id)}, headers=auth_header(learner)).status_code == 201

    rows = notifications(db, type=NotificationType.BOOKING_CONFIRMATION)
    assert [n.channel for n in rows] == [EMAIL, SMS]
    assert "Amount paid: Free" in rows[0].message
    assert notifications(db, type=NotificationType.ADMIN_PAYMENT) == []


def test_admin_cancellation_tells_the_learner_about_the_refund(
    client: TestClient, db: Session, admin_headers: dict
) -> None:
    booking, _ = paid_booking(db, make_user(db), make_slot(db, make_webinar(db), available_seats=9))

    assert client.post(f"/admin/bookings/{booking.id}/cancel", headers=admin_headers).status_code == 200

    email, sms = notifications(db, type=NotificationType.CANCELLATION)
    assert "A full refund of ₹999 has been initiated" in email.message
    assert "Refund of ₹999 initiated" in sms.message


def test_late_payment_refund_is_explained_to_the_learner(client: TestClient, db: Session) -> None:
    learner = make_user(db)
    slot = make_slot(db, make_webinar(db), capacity=1, available_seats=0)
    booking = make_booking(db, learner, slot)
    order_id = create_order(client, learner, booking).json()["order_id"]
    booking.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()
    expire_stale_bookings(db)
    slot.available_seats = 0
    db.flush()

    post_webhook(client, webhook_body("payment.captured", order_id=order_id))

    email, sms = notifications(db, type=NotificationType.REFUND)
    assert "slot filled up" in email.message
    assert sms.channel == SMS


# --- delivery -------------------------------------------------------------------


def test_dispatcher_delivers_due_notifications_once(db: Session, providers: NotificationProviders) -> None:
    booking = queue_paid_confirmation(db)

    assert dispatch_pending(db, providers) == 5
    assert dispatch_pending(db, providers) == 0

    assert sorted(m["to"] for m in providers.email.sent) == [
        "learner@example.com",
        "ops@skillcortex.in",
        "owner@skillcortex.in",
    ]
    assert sorted((m["to"], m["template_key"]) for m in providers.sms.sent) == [
        ("9000000001", "ADMIN_PAYMENT"),
        ("9876543210", "BOOKING_CONFIRMATION"),
    ]
    rows = notifications(db, booking_id=booking.id)
    assert len(rows) == 5
    assert all(n.status == NotificationStatus.SENT and n.attempts == 1 and n.sent_at for n in rows)


def test_failed_deliveries_are_retried_with_backoff_then_marked_failed(
    db: Session, providers: NotificationProviders
) -> None:
    providers.email.error = RuntimeError("SMTP server unavailable")
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)), BookingStatus.CONFIRMED)
    notify_booking_confirmed(db, booking)
    start = datetime.now(UTC)

    assert dispatch_pending(db, providers, now=start) == 1  # the SMS still goes out
    [email] = notifications(db, booking_id=booking.id, channel=EMAIL)
    assert (email.status, email.attempts, email.failure_reason) == (
        NotificationStatus.PENDING,
        1,
        "SMTP server unavailable",
    )
    assert email.next_attempt_at == start + timedelta(minutes=5)

    assert dispatch_pending(db, providers, now=start + timedelta(minutes=1)) == 0  # not due yet
    db.refresh(email)
    assert email.attempts == 1

    second_try = start + timedelta(minutes=6)
    dispatch_pending(db, providers, now=second_try)
    db.refresh(email)
    assert (email.attempts, email.next_attempt_at) == (2, second_try + timedelta(minutes=10))

    dispatch_pending(db, providers, now=start + timedelta(days=1))
    db.refresh(email)
    assert (email.status, email.attempts, email.next_attempt_at) == (NotificationStatus.FAILED, 3, None)

    db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED  # delivery failures never touch the booking


def test_dispatcher_never_sends_password_reset_rows(db: Session, providers: NotificationProviders) -> None:
    record_password_reset(db, make_user(db))

    assert dispatch_pending(db, providers) == 0
    assert providers.email.sent == []


def test_password_reset_link_is_emailed_but_never_stored(
    client: TestClient, db: Session, notifier: FakeNotifier, providers: NotificationProviders
) -> None:
    make_user(db, email="learner@example.com")

    client.post("/auth/forgot-password", json={"email": "learner@example.com"})

    [link] = notifier.reset_links
    [notification_id] = notifier.reset_notification_ids
    [row] = notifications(db, type=NotificationType.PASSWORD_RESET)
    assert row.message == REDACTED_RESET_MESSAGE
    assert link.split("token=")[1] not in (row.message + (row.subject or ""))

    assert deliver_password_reset(db, providers, notification_id, link) is True
    assert link in providers.email.sent[0]["text"]
    db.refresh(row)
    assert row.status == NotificationStatus.SENT
    assert deliver_password_reset(db, providers, notification_id, link) is False  # one-shot


def test_failed_password_reset_email_is_not_retried(db: Session, providers: NotificationProviders) -> None:
    providers.email.error = ConnectionError("SMTP down")
    row = record_password_reset(db, make_user(db))

    assert deliver_password_reset(db, providers, row.id, "http://localhost/reset?token=x") is False

    db.refresh(row)
    assert (row.status, row.failure_reason) == (NotificationStatus.FAILED, "SMTP down")


# --- viewing & retrying ---------------------------------------------------------


def test_learners_see_only_their_own_notifications(client: TestClient, db: Session) -> None:
    learner, other = make_user(db), make_user(db)
    for user in (learner, other):
        notify_booking_confirmed(db, make_booking(db, user, make_slot(db, make_webinar(db)), BookingStatus.CONFIRMED))

    body = client.get("/notifications", headers=auth_header(learner)).json()

    assert body["total"] == 2
    assert {item["channel"] for item in body["items"]} == {"EMAIL", "SMS"}
    assert "recipient_address" not in body["items"][0]


def test_admin_monitors_and_retries_notifications(
    client: TestClient, db: Session, admin_headers: dict, learner_headers: dict, notifier: FakeNotifier
) -> None:
    booking = queue_paid_confirmation(db)
    [failed] = notifications(db, booking_id=booking.id, channel=SMS, type=NotificationType.ADMIN_PAYMENT)
    failed.status = NotificationStatus.FAILED
    failed.attempts = 3
    failed.failure_reason = "MSG91 rejected the SMS: invalid template"
    db.flush()

    def total(**params) -> int:
        response = client.get("/admin/notifications", params=params, headers=admin_headers)
        assert response.status_code == 200
        return response.json()["total"]

    assert total() == 5
    assert total(status="FAILED") == 1
    assert total(type="ADMIN_PAYMENT") == 3
    assert total(channel="SMS") == 2
    assert total(q="ops@") == 1
    assert total(booking_id=str(booking.id)) == 5

    retried = client.post(f"/admin/notifications/{failed.id}/retry", headers=admin_headers)
    assert retried.status_code == 200
    assert (retried.json()["status"], retried.json()["attempts"], retried.json()["failure_reason"]) == ("PENDING", 0, None)
    assert notifier.dispatch_calls == 1

    sent = notifications(db, booking_id=booking.id, channel=EMAIL)[0]
    sent.status = NotificationStatus.SENT
    db.flush()
    assert client.post(f"/admin/notifications/{sent.id}/retry", headers=admin_headers).status_code == 409
    reset = record_password_reset(db, make_user(db))
    assert client.post(f"/admin/notifications/{reset.id}/retry", headers=admin_headers).status_code == 409
    assert client.get("/admin/notifications", headers=learner_headers).status_code == 403
