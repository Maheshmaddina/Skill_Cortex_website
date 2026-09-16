"""The database itself must enforce the V1 invariants, independent of service code."""

from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BookingStatus,
    Department,
    Notification,
    NotificationChannel,
    NotificationType,
    PaymentStatus,
    RecipientType,
    ReminderRule,
)
from app.scripts.seed import DEPARTMENTS, REMINDER_RULES, seed
from tests.factories import make_booking, make_department, make_payment, make_slot, make_user, make_webinar


def assert_violates(db: Session, action: Callable[[], None]) -> None:
    """Run `action` + flush inside a savepoint and expect the database to reject it."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            action()
            db.flush()


def test_available_seats_cannot_go_negative_or_exceed_capacity(db: Session) -> None:
    slot = make_slot(db, make_webinar(db), capacity=2)

    def set_negative() -> None:
        slot.available_seats = -1

    def set_above_capacity() -> None:
        slot.available_seats = 3

    assert_violates(db, set_negative)
    assert_violates(db, set_above_capacity)


def test_one_live_booking_per_user_per_slot(db: Session) -> None:
    user = make_user(db)
    slot = make_slot(db, make_webinar(db))
    first = make_booking(db, user, slot)

    assert_violates(db, lambda: make_booking(db, user, slot, BookingStatus.CONFIRMED))

    first.status = BookingStatus.EXPIRED
    db.flush()
    assert make_booking(db, user, slot).status == BookingStatus.PENDING


def test_one_active_payment_per_booking_but_retry_after_failure(db: Session) -> None:
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))
    first = make_payment(db, booking)

    assert_violates(db, lambda: make_payment(db, booking))

    first.status = PaymentStatus.FAILED
    db.flush()
    assert make_payment(db, booking).status == PaymentStatus.PENDING


def _notification(booking_id, type_: NotificationType, offset: int | None = None) -> Notification:
    return Notification(
        booking_id=booking_id,
        recipient_type=RecipientType.USER,
        recipient_address="learner@example.com",
        type=type_,
        channel=NotificationChannel.EMAIL,
        message="hello",
        reminder_offset_days=offset,
    )


def test_duplicate_reminder_is_rejected(db: Session) -> None:
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))
    db.add(_notification(booking.id, NotificationType.REMINDER, offset=1))
    db.flush()

    assert_violates(db, lambda: db.add(_notification(booking.id, NotificationType.REMINDER, offset=1)))

    # A different offset for the same booking is a different reminder.
    db.add(_notification(booking.id, NotificationType.REMINDER, offset=0))
    db.flush()


def test_reminder_requires_offset(db: Session) -> None:
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))

    assert_violates(db, lambda: db.add(_notification(booking.id, NotificationType.REMINDER, offset=None)))


def test_duplicate_booking_confirmation_is_rejected(db: Session) -> None:
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))
    db.add(_notification(booking.id, NotificationType.BOOKING_CONFIRMATION))
    db.flush()

    assert_violates(db, lambda: db.add(_notification(booking.id, NotificationType.BOOKING_CONFIRMATION)))


def test_email_is_unique_case_insensitively(db: Session) -> None:
    make_user(db, email="Dhanushya@Example.com")

    assert_violates(db, lambda: make_user(db, email="dhanushya@example.com"))


def test_booking_reference_is_generated(db: Session) -> None:
    booking = make_booking(db, make_user(db), make_slot(db, make_webinar(db)))
    db.refresh(booking)

    prefix, number = booking.reference.split("-")
    assert prefix == "SC"
    assert int(number) >= 10001


def test_webinar_can_belong_to_multiple_departments(db: Session) -> None:
    cse, aiml = make_department(db, "CSE test"), make_department(db, "AI/ML test")
    webinar = make_webinar(db, departments=[cse, aiml])
    db.expire_all()

    assert {d.name for d in webinar.departments} == {"CSE test", "AI/ML test"}
    assert [w.id for w in cse.webinars] == [webinar.id]


def test_seed_is_idempotent(db: Session) -> None:
    seed(db)
    seed(db)

    seeded_names = [name for name, _ in DEPARTMENTS]
    department_count = db.scalar(select(func.count()).where(Department.name.in_(seeded_names)))
    assert department_count == len(DEPARTMENTS)
    assert db.scalar(select(func.count()).select_from(ReminderRule)) == len(REMINDER_RULES)
