"""Learner-set webinars: a learner picks any date and start time for a course and we run it then.

"Set webinar" creates the session at that time (or joins one already running then) and holds
the learner's seat as a normal booking, so payment, confirmation, reminders and the admin
payment alert all work unchanged. Admins see these sessions flagged as learner-set.

A learner-set session nobody ends up paying for is withdrawn once it has been idle for an hour
(after the 15-minute hold, with room for a late payment), so it doesn't sit in the catalog.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LIVE_BOOKING_STATUSES, Booking, RecordStatus, Slot, SlotStatus, User, UserRole, Webinar
from app.services import bookings as booking_service
from app.services.bookings import BookingNotAllowed, SlotFull
from app.services.errors import ServiceError
from app.services.webinars import WebinarUnavailable

EARLIEST_START = time(7, 0)
LATEST_START = time(21, 0)
TIME_STEP_MINUTES = 30
MAX_DAYS_AHEAD = 90
LEARNER_SESSION_CAPACITY = 60
UNUSED_SESSION_GRACE = timedelta(hours=1)


class InvalidSessionTime(ServiceError):
    message = "Please choose a valid date and time."


def local_zone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def set_webinar(
    db: Session,
    user: User,
    *,
    webinar_id: UUID,
    preferred_date: date,
    preferred_time: time,
    note: str | None = None,
    now: datetime | None = None,
) -> tuple[Booking, bool]:
    """Create (or join) the session at the learner's date and time and hold their seat.

    Returns (booking, created) like `create_booking`: pressing "Set webinar" again for the same
    time returns the learner's unpaid booking instead of taking another seat.
    """
    if user.role != UserRole.USER:
        raise BookingNotAllowed
    webinar = db.get(Webinar, webinar_id)
    if webinar is None or webinar.status != RecordStatus.ACTIVE:
        raise WebinarUnavailable
    validate_session_time(preferred_date, preferred_time, now or datetime.now(UTC))

    start = datetime.combine(preferred_date, preferred_time, local_zone()).astimezone(UTC)
    # Serialise "Set webinar" for the same course and start time so two learners share one session.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"learner-session:{webinar.id}:{start.isoformat()}"))))

    slot = db.scalars(
        select(Slot)
        .where(Slot.webinar_id == webinar.id, Slot.start_at == start, Slot.status == SlotStatus.ACTIVE)
        .order_by(Slot.available_seats.desc(), Slot.created_at)
    ).first()
    if slot is None:
        slot = Slot(
            webinar=webinar,
            start_at=start,
            end_at=start + timedelta(minutes=webinar.duration_minutes),
            capacity=LEARNER_SESSION_CAPACITY,
            available_seats=LEARNER_SESSION_CAPACITY,
            set_by_user_id=user.id,
            learner_note=(note or "").strip() or None,
        )
        db.add(slot)
        db.flush()
    elif slot.available_seats == 0 and not _has_live_booking(db, user, slot):
        raise SlotFull("The session at this time is full. Please choose another time.")

    booking, created = booking_service.create_booking(db, user, slot.id)
    if created and slot.set_by_user_id not in (None, user.id) and (note or "").strip():
        _add_note(slot, f"{user.name}: {note.strip()}")
    return booking, created


def validate_session_time(preferred_date: date, preferred_time: time, now: datetime) -> None:
    today = now.astimezone(local_zone()).date()
    if preferred_date <= today:
        raise InvalidSessionTime("Please choose a date from tomorrow onwards.")
    if preferred_date > today + timedelta(days=MAX_DAYS_AHEAD):
        raise InvalidSessionTime(f"Please choose a date within the next {MAX_DAYS_AHEAD} days.")
    if not EARLIEST_START <= preferred_time <= LATEST_START:
        raise InvalidSessionTime("Please choose a start time between 7:00 AM and 9:00 PM IST.")
    if preferred_time.minute % TIME_STEP_MINUTES or preferred_time.second or preferred_time.microsecond:
        raise InvalidSessionTime("Please choose a start time on the hour or half hour.")


def withdraw_unused_learner_sessions(db: Session, now: datetime | None = None) -> int:
    """Deactivate upcoming learner-set sessions that have had no pending or confirmed booking for an hour."""
    now = now or datetime.now(UTC)
    live_booking = exists().where(Booking.slot_id == Slot.id, Booking.status.in_(LIVE_BOOKING_STATUSES))
    recent_booking = exists().where(Booking.slot_id == Slot.id, Booking.updated_at > now - UNUSED_SESSION_GRACE)
    result = db.execute(
        update(Slot)
        .where(
            Slot.set_by_user_id.is_not(None),
            Slot.status == SlotStatus.ACTIVE,
            Slot.start_at > now,
            Slot.created_at <= now - UNUSED_SESSION_GRACE,
            ~live_booking,
            ~recent_booking,
        )
        .values(status=SlotStatus.INACTIVE)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def _add_note(slot: Slot, line: str) -> None:
    """Learners joining a learner-set session can leave the mentor a note too (kept within the column size)."""
    combined = f"{slot.learner_note}\n{line}" if slot.learner_note else line
    slot.learner_note = combined[:500]


def _has_live_booking(db: Session, user: User, slot: Slot) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    Booking.user_id == user.id, Booking.slot_id == slot.id, Booking.status.in_(LIVE_BOOKING_STATUSES)
                )
            )
        )
    )
