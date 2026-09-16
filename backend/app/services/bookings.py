"""Bookings and seat holds (decision D4).

A seat is taken when the booking is created, by one conditional UPDATE — the database row
lock plus the WHERE clause make overbooking impossible under concurrency. An unpaid (PENDING)
booking holds its seat until `expires_at`; the expiry job (or an inline sweep when a slot looks
full) releases it.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import (
    LIVE_BOOKING_STATUSES,
    Booking,
    BookingStatus,
    Payment,
    PaymentStatus,
    RecordStatus,
    Slot,
    SlotStatus,
    User,
    UserRole,
)
from app.services.errors import Conflict, NotFound, ServiceError
from app.services.notifications import notify_booking_confirmed
from app.services.slots import SlotNotFound
from app.services.webinars import WebinarUnavailable
from app.utils.query import LIKE_ESCAPE, contains_pattern, count_rows

BookingScope = Literal["upcoming", "past"]


class BookingNotFound(NotFound):
    message = "Booking not found."


class BookingNotAllowed(ServiceError):
    status_code = 403
    message = "Only learner accounts can book webinars."


class AlreadyBooked(Conflict):
    message = "You already have a confirmed booking for this slot."


class SlotFull(Conflict):
    message = "This slot is full. Please choose another available slot."


class SlotUnavailable(Conflict):
    message = "This slot is no longer available. Please choose another slot."


class BookingNotCancellable(Conflict):
    message = "Only unpaid bookings can be cancelled. Please contact support about a paid booking."


# --- learner actions -----------------------------------------------------------


def create_booking(db: Session, user: User, slot_id: UUID) -> tuple[Booking, bool]:
    """Hold a seat and create the booking. Returns (booking, created).

    If the learner already has an unexpired unpaid booking for this slot it is returned
    instead (created=False), so retrying "Book now" doesn't take a second seat.
    """
    if user.role != UserRole.USER:
        raise BookingNotAllowed
    slot = db.get(Slot, slot_id)
    if slot is None:
        raise SlotNotFound
    webinar = slot.webinar
    if webinar.status != RecordStatus.ACTIVE:
        raise WebinarUnavailable

    now = datetime.now(UTC)
    existing = db.scalar(
        select(Booking).where(
            Booking.user_id == user.id, Booking.slot_id == slot.id, Booking.status.in_(LIVE_BOOKING_STATUSES)
        )
    )
    if existing is not None:
        if existing.status == BookingStatus.CONFIRMED:
            raise AlreadyBooked
        if existing.expires_at is not None and existing.expires_at > now:
            return existing, False
        # Expired hold the job hasn't swept yet; it's released by the sweep below or here.

    if not hold_seat(db, slot.id):
        # Expired holds may still occupy seats if the expiry job hasn't run yet.
        if not (expire_stale_bookings(db, now, slot_id=slot.id) and hold_seat(db, slot.id)):
            db.refresh(slot)
            if slot.status != SlotStatus.ACTIVE or slot.start_at <= now:
                raise SlotUnavailable
            raise SlotFull
    elif existing is not None:
        expire_stale_bookings(db, now, slot_id=slot.id)

    is_free = webinar.price_paise == 0
    booking = Booking(
        user=user,
        webinar=webinar,
        slot=slot,
        amount_paise=webinar.price_paise,  # price snapshot (decision D10)
        status=BookingStatus.CONFIRMED if is_free else BookingStatus.PENDING,
        expires_at=None if is_free else now + timedelta(minutes=get_settings().booking_hold_minutes),
        confirmed_at=now if is_free else None,
    )
    try:
        with db.begin_nested():
            db.add(booking)
            db.flush()
    except IntegrityError as exc:  # a concurrent request booked this slot for the same learner
        release_seat(db, slot.id)
        raise AlreadyBooked from exc
    if is_free:
        notify_booking_confirmed(db, booking)
    return booking, True


def cancel_unpaid_booking(db: Session, user: User, booking_id: UUID) -> Booking:
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id).with_for_update()
    )
    if booking is None:
        raise BookingNotFound
    if booking.status != BookingStatus.PENDING:
        raise BookingNotCancellable
    release_hold(db, booking, BookingStatus.CANCELLED, "Booking cancelled by the learner.", datetime.now(UTC))
    db.flush()
    return booking


def get_user_booking(db: Session, user: User, booking_id: UUID) -> Booking:
    booking = db.scalar(_with_details(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id)))
    if booking is None:
        raise BookingNotFound  # also for other learners' bookings, so ids can't be probed
    return booking


def list_user_bookings(
    db: Session, user: User, *, scope: BookingScope | None, offset: int, limit: int
) -> tuple[list[Booking], int]:
    """`upcoming`: confirmed or still-held bookings whose session hasn't ended (soonest first).
    `past`: everything else (most recent first)."""
    now = datetime.now(UTC)
    query = select(Booking).join(Booking.slot).where(Booking.user_id == user.id)
    upcoming = and_(
        Slot.end_at > now,
        or_(
            Booking.status == BookingStatus.CONFIRMED,
            and_(Booking.status == BookingStatus.PENDING, Booking.expires_at > now),
        ),
    )
    if scope == "upcoming":
        query = query.where(upcoming).order_by(Slot.start_at, Booking.id)
    elif scope == "past":
        query = query.where(~upcoming).order_by(Slot.start_at.desc(), Booking.id)
    else:
        query = query.order_by(Booking.created_at.desc(), Booking.id)

    total = count_rows(db, query)
    bookings = db.scalars(_with_details(query).offset(offset).limit(limit)).all()
    return list(bookings), total


# --- admin ---------------------------------------------------------------------


def get_booking(db: Session, booking_id: UUID) -> Booking:
    booking = db.scalar(_with_details(select(Booking).where(Booking.id == booking_id)))
    if booking is None:
        raise BookingNotFound
    return booking


def list_bookings(
    db: Session,
    *,
    status: BookingStatus | None,
    webinar_id: UUID | None,
    slot_id: UUID | None,
    user_id: UUID | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Booking], int]:
    query = select(Booking).join(Booking.user)
    if status is not None:
        query = query.where(Booking.status == status)
    if webinar_id is not None:
        query = query.where(Booking.webinar_id == webinar_id)
    if slot_id is not None:
        query = query.where(Booking.slot_id == slot_id)
    if user_id is not None:
        query = query.where(Booking.user_id == user_id)
    if q:
        pattern = contains_pattern(q)
        query = query.where(
            or_(
                Booking.reference.ilike(pattern, escape=LIKE_ESCAPE),
                User.email.ilike(pattern, escape=LIKE_ESCAPE),
                User.name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    total = count_rows(db, query)
    bookings = db.scalars(
        _with_details(query).order_by(Booking.created_at.desc(), Booking.id).offset(offset).limit(limit)
    ).all()
    return list(bookings), total


# --- background jobs -----------------------------------------------------------


def expire_stale_bookings(db: Session, now: datetime | None = None, *, slot_id: UUID | None = None) -> int:
    """Release seats held by unpaid bookings past `expires_at`. Safe to run concurrently."""
    now = now or datetime.now(UTC)
    query = select(Booking).where(Booking.status == BookingStatus.PENDING, Booking.expires_at <= now)
    if slot_id is not None:
        query = query.where(Booking.slot_id == slot_id)
    stale = db.scalars(query.with_for_update(skip_locked=True)).all()
    for booking in stale:
        release_hold(db, booking, BookingStatus.EXPIRED, "Payment window expired.", now)
    db.flush()
    return len(stale)


def complete_finished_bookings(db: Session, now: datetime | None = None) -> int:
    """Mark confirmed bookings whose session has ended as COMPLETED."""
    now = now or datetime.now(UTC)
    ended_slots = select(Slot.id).where(Slot.end_at <= now)
    result = db.execute(
        update(Booking)
        .where(Booking.status == BookingStatus.CONFIRMED, Booking.slot_id.in_(ended_slots))
        .values(status=BookingStatus.COMPLETED)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount


# --- seat primitives (also used by payments) -----------------------------------


def hold_seat(db: Session, slot_id: UUID) -> bool:
    held = db.execute(
        update(Slot)
        .where(
            Slot.id == slot_id,
            Slot.status == SlotStatus.ACTIVE,
            Slot.available_seats > 0,
            Slot.start_at > func.now(),
        )
        .values(available_seats=Slot.available_seats - 1)
        .returning(Slot.id)
        .execution_options(synchronize_session="fetch")
    ).first()
    return held is not None


def release_seat(db: Session, slot_id: UUID) -> None:
    db.execute(
        update(Slot)
        .where(Slot.id == slot_id)
        .values(available_seats=Slot.available_seats + 1)
        .execution_options(synchronize_session="fetch")
    )


def release_hold(db: Session, booking: Booking, status: BookingStatus, reason: str, now: datetime) -> None:
    booking.status = status
    if status == BookingStatus.CANCELLED:
        booking.cancelled_at = now
    release_seat(db, booking.slot_id)
    db.execute(
        update(Payment)
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING)
        .values(status=PaymentStatus.FAILED, failure_reason=reason)
        .execution_options(synchronize_session="fetch")
    )


def has_other_live_booking(db: Session, booking: Booking) -> bool:
    return bool(
        db.scalar(
            select(Booking.id).where(
                Booking.user_id == booking.user_id,
                Booking.slot_id == booking.slot_id,
                Booking.status.in_(LIVE_BOOKING_STATUSES),
                Booking.id != booking.id,
            )
        )
    )


def _with_details(query: Select) -> Select:
    return query.options(
        selectinload(Booking.webinar),
        selectinload(Booking.slot),
        selectinload(Booking.payments),
        selectinload(Booking.user),
    )
