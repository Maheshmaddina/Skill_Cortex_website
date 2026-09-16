from datetime import UTC, datetime, time, timedelta

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
    ReminderRule,
)
from app.scripts.seed import seed
from app.services.notification_providers import NotificationProviders
from app.services.notifications import dispatch_pending
from app.services.reminders import enqueue_due_reminders, reminder_due_at
from tests.factories import make_booking, make_slot, make_user, make_webinar
from tests.fakes import FakeEmailProvider, FakeSmsProvider

# Session: Sun 20 Sep 2026, 10:00 AM IST (04:30 UTC). Default rules: 3/2/1 days at 09:00 IST, same day at 08:00.
SESSION_START = datetime(2026, 9, 20, 4, 30, tzinfo=UTC)
IST_0900_UTC = time(3, 30)


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


@pytest.fixture
def rules(db: Session) -> dict[int, ReminderRule]:
    seed(db)
    return {rule.offset_days: rule for rule in db.scalars(select(ReminderRule))}


def confirmed_booking(
    db: Session, *, start_at: datetime = SESSION_START, confirmed_at: datetime = utc(10, 12)
) -> Booking:
    slot = make_slot(db, make_webinar(db, title="Python"))
    slot.start_at, slot.end_at = start_at, start_at + timedelta(hours=1)
    booking = make_booking(db, make_user(db), slot, BookingStatus.CONFIRMED)
    booking.confirmed_at = confirmed_at
    db.flush()
    return booking


def reminders(db: Session, booking: Booking) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.booking_id == booking.id, Notification.type == NotificationType.REMINDER)
            .order_by(Notification.reminder_offset_days.desc(), Notification.channel)
        )
    )


# --- when reminders are due -----------------------------------------------------


def test_due_times_follow_the_ist_schedule(rules: dict[int, ReminderRule]) -> None:
    assert reminder_due_at(rules[3], SESSION_START) == utc(17, 3, 30)  # Thu 09:00 IST
    assert reminder_due_at(rules[2], SESSION_START) == utc(18, 3, 30)
    assert reminder_due_at(rules[1], SESSION_START) == utc(19, 3, 30)
    assert reminder_due_at(rules[0], SESSION_START) == utc(20, 2, 30)  # 08:00 IST, 2h before a 10:00 session


def test_same_day_reminder_moves_earlier_for_early_sessions(rules: dict[int, ReminderRule]) -> None:
    seven_am_ist = utc(20, 1, 30)

    assert reminder_due_at(rules[0], seven_am_ist) == utc(19, 23, 30)  # 05:00 IST, two hours before


# --- queueing -------------------------------------------------------------------


def test_queues_the_due_reminder_once(db: Session, rules: dict) -> None:
    booking = confirmed_booking(db)

    assert enqueue_due_reminders(db, now=utc(17, 3, 29)) == 0  # a minute early
    assert enqueue_due_reminders(db, now=utc(17, 3, 35)) == 2  # email + SMS
    assert enqueue_due_reminders(db, now=utc(17, 3, 40)) == 0  # already queued

    email, sms = reminders(db, booking)
    assert (email.reminder_offset_days, email.channel, sms.channel) == (3, NotificationChannel.EMAIL, NotificationChannel.SMS)
    assert "your Python webinar is in 3 days (Sun, 20 Sep 2026, 10:00 AM IST)" in email.message
    assert sms.payload["when"].startswith("is in 3 days")


def test_each_offset_is_sent_in_turn(db: Session, rules: dict) -> None:
    booking = confirmed_booking(db)

    for now in (utc(17, 3, 35), utc(18, 3, 35), utc(19, 3, 35), utc(20, 2, 35)):
        enqueue_due_reminders(db, now=now)

    rows = reminders(db, booking)
    assert [n.reminder_offset_days for n in rows if n.channel == NotificationChannel.EMAIL] == [3, 2, 1, 0]
    texts = {n.reminder_offset_days: n.message for n in rows if n.channel == NotificationChannel.SMS}
    assert "is tomorrow at 10:00 AM IST" in texts[1]
    assert "starts today at 10:00 AM IST" in texts[0]


def test_only_the_latest_due_reminder_is_sent_after_downtime(db: Session, rules: dict) -> None:
    booking = confirmed_booking(db)

    enqueue_due_reminders(db, now=utc(19, 4, 0))  # scheduler was down for the 3- and 2-day reminders

    assert {n.reminder_offset_days for n in reminders(db, booking)} == {1}


def test_reminders_due_before_confirmation_are_skipped(db: Session, rules: dict) -> None:
    booking = confirmed_booking(db, confirmed_at=utc(18, 12))  # booked after the 2-day reminder time

    assert enqueue_due_reminders(db, now=utc(18, 12, 5)) == 0
    assert enqueue_due_reminders(db, now=utc(19, 3, 35)) == 2
    assert {n.reminder_offset_days for n in reminders(db, booking)} == {1}


def test_only_confirmed_upcoming_bookings_get_reminders(db: Session, rules: dict) -> None:
    pending = confirmed_booking(db)
    pending.status = BookingStatus.PENDING
    cancelled = confirmed_booking(db)
    cancelled.status = BookingStatus.CANCELLED
    db.flush()

    assert enqueue_due_reminders(db, now=utc(17, 3, 35)) == 0
    assert enqueue_due_reminders(db, now=utc(20, 5, 0)) == 0  # session already started


def test_rule_channels_and_active_flag_are_respected(db: Session, rules: dict) -> None:
    rules[3].send_sms = False
    rules[2].active = False
    db.flush()
    booking = confirmed_booking(db)

    assert enqueue_due_reminders(db, now=utc(17, 3, 35)) == 1
    assert enqueue_due_reminders(db, now=utc(18, 3, 35)) == 0  # 2-day rule paused; 3-day already sent

    [email] = reminders(db, booking)
    assert (email.reminder_offset_days, email.channel) == (3, NotificationChannel.EMAIL)


def test_reminder_for_a_booking_cancelled_after_queueing_is_not_sent(db: Session, rules: dict) -> None:
    providers = NotificationProviders(email=FakeEmailProvider(), sms=FakeSmsProvider())
    booking = confirmed_booking(db)
    enqueue_due_reminders(db, now=utc(17, 3, 35))
    booking.status = BookingStatus.CANCELLED
    db.flush()

    assert dispatch_pending(db, providers) == 0

    assert providers.email.sent == providers.sms.sent == []
    assert {(n.status, n.failure_reason) for n in reminders(db, booking)} == {
        (NotificationStatus.FAILED, "Booking is no longer confirmed.")
    }


def test_queued_reminders_are_delivered(db: Session, rules: dict) -> None:
    providers = NotificationProviders(email=FakeEmailProvider(), sms=FakeSmsProvider())
    booking = confirmed_booking(db)
    enqueue_due_reminders(db, now=utc(19, 3, 35))

    assert dispatch_pending(db, providers) == 2

    assert providers.email.sent[0]["subject"] == "Reminder: Python is tomorrow at 10:00 AM IST"
    assert providers.sms.sent[0]["template_key"] == "REMINDER"
    assert all(n.status == NotificationStatus.SENT for n in reminders(db, booking))


# --- admin rule management ------------------------------------------------------


def test_admin_manages_the_reminder_schedule(
    client: TestClient, db: Session, rules: dict, admin_headers: dict, learner_headers: dict
) -> None:
    listed = client.get("/admin/reminder-rules", headers=admin_headers).json()
    assert [(r["offset_days"], r["send_time_local"]) for r in listed] == [
        (3, "09:00:00"),
        (2, "09:00:00"),
        (1, "09:00:00"),
        (0, "08:00:00"),
    ]

    created = client.post(
        "/admin/reminder-rules", json={"offset_days": 7, "send_time_local": "18:30"}, headers=admin_headers
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert (created.json()["send_time_local"], created.json()["send_sms"]) == ("18:30:00", True)

    duplicate = client.post("/admin/reminder-rules", json={"offset_days": 7, "send_time_local": "09:00"}, headers=admin_headers)
    assert duplicate.status_code == 409
    no_channels = client.post(
        "/admin/reminder-rules",
        json={"offset_days": 5, "send_time_local": "09:00", "send_email": False, "send_sms": False},
        headers=admin_headers,
    )
    assert no_channels.status_code == 400
    assert client.post("/admin/reminder-rules", json={"offset_days": 31, "send_time_local": "09:00"}, headers=admin_headers).status_code == 422

    updated = client.put(f"/admin/reminder-rules/{rule_id}", json={"send_sms": False, "active": False}, headers=admin_headers)
    assert (updated.json()["send_sms"], updated.json()["active"]) == (False, False)
    cleared = client.put(f"/admin/reminder-rules/{rule_id}", json={"send_email": False}, headers=admin_headers)
    assert cleared.status_code == 400

    assert client.delete(f"/admin/reminder-rules/{rule_id}", headers=admin_headers).status_code == 204
    assert len(client.get("/admin/reminder-rules", headers=admin_headers).json()) == 4
    assert client.get("/admin/reminder-rules", headers=learner_headers).status_code == 403
