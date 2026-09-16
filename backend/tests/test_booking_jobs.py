from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import BookingStatus, PaymentStatus
from app.scheduler.__main__ import build_scheduler
from app.services.bookings import complete_finished_bookings, expire_stale_bookings
from tests.factories import make_booking, make_payment, make_slot, make_user, make_webinar


def test_expiry_job_releases_seats_and_fails_pending_payments(db: Session) -> None:
    slot = make_slot(db, make_webinar(db), capacity=5, available_seats=3)  # two seats held
    stale = make_booking(db, make_user(db), slot, expires_in=timedelta(minutes=-1))
    fresh = make_booking(db, make_user(db), slot, expires_in=timedelta(minutes=10))
    stale_payment = make_payment(db, stale)

    assert expire_stale_bookings(db) == 1
    assert expire_stale_bookings(db) == 0  # idempotent

    for obj in (stale, fresh, slot, stale_payment):
        db.refresh(obj)
    assert stale.status == BookingStatus.EXPIRED
    assert fresh.status == BookingStatus.PENDING
    assert slot.available_seats == 4
    assert stale_payment.status == PaymentStatus.FAILED
    assert stale_payment.failure_reason == "Payment window expired."


def test_expiry_job_ignores_confirmed_bookings(db: Session) -> None:
    slot = make_slot(db, make_webinar(db), capacity=5, available_seats=4)
    confirmed = make_booking(db, make_user(db), slot, BookingStatus.CONFIRMED)

    assert expire_stale_bookings(db) == 0
    db.refresh(confirmed)
    assert confirmed.status == BookingStatus.CONFIRMED


def test_completion_job_marks_finished_confirmed_bookings(db: Session) -> None:
    webinar = make_webinar(db)
    finished = make_booking(db, make_user(db), make_slot(db, webinar, starts_in=timedelta(hours=-2)), BookingStatus.CONFIRMED)
    in_progress = make_booking(
        db, make_user(db), make_slot(db, webinar, starts_in=timedelta(minutes=-30)), BookingStatus.CONFIRMED
    )
    upcoming = make_booking(db, make_user(db), make_slot(db, webinar), BookingStatus.CONFIRMED)

    assert complete_finished_bookings(db) == 1

    for booking in (finished, in_progress, upcoming):
        db.refresh(booking)
    assert finished.status == BookingStatus.COMPLETED
    assert in_progress.status == BookingStatus.CONFIRMED
    assert upcoming.status == BookingStatus.CONFIRMED


def test_scheduler_registers_booking_jobs() -> None:
    scheduler = build_scheduler()

    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert set(jobs) == {
        "expire_stale_bookings",
        "complete_finished_bookings",
        "dispatch_notifications",
        "send_reminders",
        "purge_rate_limits",
    }
    assert jobs["expire_stale_bookings"].trigger.interval == timedelta(minutes=1)
    assert jobs["send_reminders"].trigger.interval == timedelta(minutes=5)
