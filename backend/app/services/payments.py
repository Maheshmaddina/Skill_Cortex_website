"""Razorpay payment lifecycle (decision D5).

Both the Checkout `verify` call and the webhook funnel into `confirm_payment`, which locks the
payment row and is idempotent, so a booking is confirmed exactly once whichever arrives first.
A booking is only confirmed after server-side verification (BR-05/BR-06).
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Select, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Booking, BookingStatus, Payment, PaymentEvent, PaymentStatus, User
from app.services.bookings import BookingNotFound, has_other_live_booking, hold_seat
from app.services.errors import Conflict, NotFound, ServiceError
from app.services.notifications import notify_booking_confirmed, notify_payment_refunded
from app.services.razorpay import PaymentGateway, is_valid_checkout_signature, is_valid_webhook_signature
from app.utils.query import LIKE_ESCAPE, contains_pattern, count_rows

logger = logging.getLogger("uvicorn.error")

CURRENCY = "INR"


class PaymentOutcome(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    REFUNDED = "refunded"
    AMOUNT_MISMATCH = "amount_mismatch"
    FAILED = "failed"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"


OUTCOME_MESSAGES = {
    PaymentOutcome.CONFIRMED: "Payment successful. Your booking is confirmed.",
    PaymentOutcome.ALREADY_CONFIRMED: "Payment successful. Your booking is confirmed.",
    PaymentOutcome.REFUNDED: (
        "Your payment arrived after the seat hold expired and the slot is now full. "
        "A full refund has been initiated."
    ),
    PaymentOutcome.AMOUNT_MISMATCH: "Your payment is being verified. Please check your booking status shortly.",
}


class AlreadyPaid(Conflict):
    message = "This booking is already paid."


class BookingNotPayable(Conflict):
    message = "This booking has expired. Please book the slot again."


class InvalidPaymentSignature(ServiceError):
    message = "Payment could not be verified. If money was deducted, it will be confirmed or refunded automatically."


class PaymentNotFound(NotFound):
    message = "Payment not found."


class InvalidWebhook(ServiceError):
    message = "Invalid webhook."


@dataclass(frozen=True)
class CheckoutSession:
    key_id: str
    payment: Payment
    booking: Booking


# --- learner checkout ----------------------------------------------------------


def create_checkout_order(db: Session, user: User, booking_id: UUID, gateway: PaymentGateway) -> CheckoutSession:
    """Create (or reuse) the Razorpay order for an unpaid booking."""
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id).with_for_update())
    if booking is None:
        raise BookingNotFound
    if booking.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED):
        raise AlreadyPaid
    if booking.status != BookingStatus.PENDING or booking.expires_at is None or booking.expires_at <= datetime.now(UTC):
        raise BookingNotPayable

    # One order per attempt: Checkout lets the learner retry on the same order.
    payment = db.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING)
    )
    if payment is None:
        order = gateway.create_order(
            amount_paise=booking.amount_paise,
            currency=CURRENCY,
            receipt=booking.reference,
            notes={"booking_id": str(booking.id), "booking_reference": booking.reference},
        )
        payment = Payment(
            booking=booking, razorpay_order_id=order.id, amount_paise=booking.amount_paise, currency=order.currency
        )
        db.add(payment)
        db.flush()
    return CheckoutSession(key_id=get_settings().razorpay_key_id, payment=payment, booking=booking)


def verify_checkout_payment(
    db: Session, user: User, *, order_id: str, payment_id: str, signature: str, gateway: PaymentGateway
) -> tuple[PaymentOutcome, Booking]:
    payment = db.scalar(
        select(Payment)
        .join(Payment.booking)
        .where(Payment.razorpay_order_id == order_id, Booking.user_id == user.id)
        .with_for_update(of=Payment)
    )
    if payment is None:
        raise PaymentNotFound
    if not is_valid_checkout_signature(order_id, payment_id, signature, get_settings().razorpay_key_secret):
        logger.warning("Rejected Checkout signature for order %s", order_id)
        raise InvalidPaymentSignature

    outcome = confirm_payment(
        db, payment, razorpay_payment_id=payment_id, amount_paise=None, gateway=gateway, signature=signature
    )
    return outcome, payment.booking


# --- webhook -------------------------------------------------------------------


def process_webhook(
    db: Session, *, body: bytes, signature: str | None, event_id: str | None, gateway: PaymentGateway
) -> PaymentOutcome:
    """Handle a Razorpay webhook delivery. Deliveries are recorded in payment_events and
    replays (same X-Razorpay-Event-Id) are acknowledged without reprocessing."""
    if not signature or not is_valid_webhook_signature(body, signature, get_settings().razorpay_webhook_secret):
        raise InvalidWebhook("Invalid webhook signature.")
    try:
        event = json.loads(body)
        event_type = str(event["event"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidWebhook("Malformed webhook payload.") from exc

    record = PaymentEvent(
        razorpay_event_id=(event_id or hashlib.sha256(body).hexdigest())[:64],
        event_type=event_type[:64],
        payload=event,
        signature_valid=True,
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        return PaymentOutcome.DUPLICATE

    outcome = _dispatch_event(db, event_type, event, gateway)
    record.processed_at = datetime.now(UTC)
    db.flush()
    return outcome


def _dispatch_event(db: Session, event_type: str, event: dict[str, Any], gateway: PaymentGateway) -> PaymentOutcome:
    if event_type not in ("payment.captured", "order.paid", "payment.failed"):
        return PaymentOutcome.IGNORED
    try:
        entity = event["payload"]["payment"]["entity"]
        order_id, payment_id = entity["order_id"], entity["id"]
    except (KeyError, TypeError):
        return PaymentOutcome.IGNORED

    payment = db.scalar(select(Payment).where(Payment.razorpay_order_id == order_id).with_for_update())
    if payment is None:
        return PaymentOutcome.IGNORED  # not an order we created

    if event_type == "payment.failed":
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = entity.get("error_description") or "Payment failed."
            db.flush()
        return PaymentOutcome.FAILED

    return confirm_payment(
        db, payment, razorpay_payment_id=payment_id, amount_paise=entity.get("amount"), gateway=gateway
    )


# --- confirmation & refunds ----------------------------------------------------


def confirm_payment(
    db: Session,
    payment: Payment,
    *,
    razorpay_payment_id: str,
    amount_paise: int | None,
    gateway: PaymentGateway,
    signature: str | None = None,
) -> PaymentOutcome:
    """Idempotently apply a verified successful payment. The caller must hold a row lock on `payment`.

    If the seat hold was already released (decision D4), the booking is revived when a seat is
    free; otherwise the money is refunded.
    """
    if payment.status == PaymentStatus.PAID:
        return PaymentOutcome.ALREADY_CONFIRMED
    if payment.status == PaymentStatus.REFUNDED:
        return PaymentOutcome.REFUNDED
    if amount_paise is not None and amount_paise != payment.amount_paise:
        payment.failure_reason = f"Amount mismatch: expected {payment.amount_paise}, received {amount_paise}."
        logger.error("Payment %s: %s", payment.id, payment.failure_reason)
        db.flush()
        return PaymentOutcome.AMOUNT_MISMATCH

    now = datetime.now(UTC)
    booking = db.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
    payment.razorpay_payment_id = razorpay_payment_id
    if signature is not None:
        payment.razorpay_signature = signature

    seat_secured = booking.status == BookingStatus.PENDING or (
        booking.status == BookingStatus.EXPIRED
        and not has_other_live_booking(db, booking)
        and hold_seat(db, booking.slot_id)
    )
    if not seat_secured:
        refund_payment(db, payment, booking, gateway, reason="Seat no longer available when payment completed.")
        if booking.status == BookingStatus.EXPIRED:
            booking.status = BookingStatus.FAILED
        db.flush()
        notify_payment_refunded(db, booking, payment)
        return PaymentOutcome.REFUNDED

    # Any other open order for this booking is now moot (and would violate the one-active-payment index).
    db.execute(
        update(Payment)
        .where(Payment.booking_id == booking.id, Payment.id != payment.id, Payment.status == PaymentStatus.PENDING)
        .values(status=PaymentStatus.FAILED, failure_reason="Superseded by another successful payment.")
        .execution_options(synchronize_session="fetch")
    )
    payment.status = PaymentStatus.PAID
    payment.paid_at = now
    payment.failure_reason = None
    booking.status = BookingStatus.CONFIRMED
    booking.confirmed_at = now
    booking.expires_at = None
    db.flush()
    notify_booking_confirmed(db, booking, payment)
    return PaymentOutcome.CONFIRMED


def refund_payment(db: Session, payment: Payment, booking: Booking, gateway: PaymentGateway, *, reason: str) -> None:
    """Refund in full via Razorpay, then record it. The gateway call comes first, so a gateway
    failure raises before anything is changed."""
    if payment.amount_paise > 0 and payment.razorpay_payment_id:
        payment.razorpay_refund_id = gateway.refund_payment(
            payment_id=payment.razorpay_payment_id,
            amount_paise=payment.amount_paise,
            notes={"booking_reference": booking.reference, "reason": reason[:250]},
        )
    payment.status = PaymentStatus.REFUNDED
    payment.refunded_at = datetime.now(UTC)
    payment.failure_reason = reason
    db.flush()


# --- admin ---------------------------------------------------------------------


def get_payment(db: Session, payment_id: UUID) -> Payment:
    payment = db.scalar(_with_details(select(Payment).where(Payment.id == payment_id)))
    if payment is None:
        raise PaymentNotFound
    return payment


def list_payments(
    db: Session,
    *,
    status: PaymentStatus | None,
    booking_id: UUID | None,
    q: str | None,
    offset: int,
    limit: int,
    user_id: UUID | None = None,
) -> tuple[list[Payment], int]:
    query = select(Payment).join(Payment.booking).join(Booking.user)
    if status is not None:
        query = query.where(Payment.status == status)
    if booking_id is not None:
        query = query.where(Payment.booking_id == booking_id)
    if user_id is not None:
        query = query.where(Booking.user_id == user_id)
    if q:
        pattern = contains_pattern(q)
        query = query.where(
            or_(
                Payment.razorpay_order_id.ilike(pattern, escape=LIKE_ESCAPE),
                Payment.razorpay_payment_id.ilike(pattern, escape=LIKE_ESCAPE),
                Booking.reference.ilike(pattern, escape=LIKE_ESCAPE),
                User.email.ilike(pattern, escape=LIKE_ESCAPE),
                User.name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    total = count_rows(db, query)
    payments = db.scalars(
        _with_details(query).order_by(Payment.created_at.desc(), Payment.id).offset(offset).limit(limit)
    ).all()
    return list(payments), total


def _with_details(query: Select) -> Select:
    booking = selectinload(Payment.booking)
    return query.options(booking.selectinload(Booking.user), booking.selectinload(Booking.webinar))
