"""Admin cancellations with refunds (decision D7)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LIVE_BOOKING_STATUSES, Booking, BookingStatus, Payment, PaymentStatus, SlotStatus
from app.services.bookings import BookingNotFound, release_hold, release_seat
from app.services.errors import Conflict
from app.services.notifications import notify_booking_cancelled
from app.services.payments import refund_payment
from app.services.razorpay import PaymentGateway
from app.services.slots import get_slot

ADMIN_CANCELLATION_REASON = "Booking cancelled by an administrator."


class BookingNotCancellableByAdmin(Conflict):
    message = "Only pending or confirmed bookings can be cancelled."


def cancel_booking_as_admin(db: Session, booking_id: UUID, gateway: PaymentGateway) -> tuple[Booking, bool]:
    """Cancel a pending or confirmed booking, refunding a paid one. Returns (booking, refunded).

    Callers should commit right after each call: a refund is an external side effect that
    must not be rolled back with a later failure.
    """
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise BookingNotFound
    now = datetime.now(UTC)

    if booking.status == BookingStatus.PENDING:
        release_hold(db, booking, BookingStatus.CANCELLED, ADMIN_CANCELLATION_REASON, now)
        db.flush()
        notify_booking_cancelled(db, booking, refunded=False)
        return booking, False
    if booking.status != BookingStatus.CONFIRMED:
        raise BookingNotCancellableByAdmin

    paid = db.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.PAID).with_for_update()
    )
    refunded = False
    if paid is not None:
        refund_payment(db, paid, booking, gateway, reason=ADMIN_CANCELLATION_REASON)
        refunded = paid.amount_paise > 0
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    release_seat(db, booking.slot_id)
    db.flush()
    notify_booking_cancelled(db, booking, refunded=refunded)
    return booking, refunded


def begin_slot_cancellation(db: Session, slot_id: UUID) -> list[UUID]:
    """Mark the slot CANCELLED (so no new seats can be held) and return its live booking ids,
    which the caller then cancels one at a time."""
    slot = get_slot(db, slot_id, for_update=True)
    slot.status = SlotStatus.CANCELLED
    db.flush()
    return list(
        db.scalars(
            select(Booking.id)
            .where(Booking.slot_id == slot.id, Booking.status.in_(LIVE_BOOKING_STATUSES))
            .order_by(Booking.created_at)
        )
    )
