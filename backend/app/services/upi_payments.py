"""Direct UPI payments (QR code / UPI ID), for when the gateway's UPI isn't available.

The learner pays the business UPI ID from any UPI app and submits the transaction reference
(UTR). Nothing is confirmed on the learner's word: the seat stays held while an admin checks the
money arrived, then confirms (booking CONFIRMED + notifications) or rejects (learner gets a short
window to correct the reference). Card/netbanking still go through Razorpay.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Booking, BookingStatus, Payment, PaymentMethod, PaymentStatus, User
from app.services.bookings import BookingNotFound, has_other_live_booking, hold_seat
from app.services.errors import Conflict, ServiceError
from app.services.notifications import notify_booking_confirmed
from app.services.payments import AlreadyPaid, BookingNotPayable, PaymentNotFound

UTR_PATTERN = re.compile(r"^\d{12}$")
RETRY_WINDOW = timedelta(minutes=30)


class UpiNotAvailable(ServiceError):
    status_code = 503
    message = "UPI payments are not available right now. Please pay by card or netbanking."


class InvalidUtr(ServiceError):
    message = "Enter the 12-digit UPI transaction ID (UTR / UPI Ref No.) shown in your UPI app."


class UtrAlreadyUsed(Conflict):
    message = "This UPI transaction ID has already been submitted. Please check it and try again."


class UpiAlreadySubmitted(Conflict):
    message = "Your UPI payment is already being verified."


class UpiPaymentNotReviewable(Conflict):
    message = "Only UPI payments waiting for verification can be confirmed or rejected."


@dataclass(frozen=True)
class UpiDetails:
    upi_id: str
    payee_name: str
    amount_paise: int
    booking_reference: str
    upi_uri: str


def upi_details(db: Session, user: User, booking_id: UUID) -> UpiDetails:
    """What the learner needs to pay by UPI: the UPI ID and a upi://pay link for the QR code."""
    settings = get_settings()
    if not settings.upi_id:
        raise UpiNotAvailable
    booking = _user_booking(db, user, booking_id)
    if booking.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED):
        raise AlreadyPaid
    if booking.status != BookingStatus.PENDING or booking.expires_at is None or booking.expires_at <= datetime.now(UTC):
        raise BookingNotPayable
    amount = f"{booking.amount_paise // 100}.{booking.amount_paise % 100:02d}"
    query = urlencode(
        {
            "pa": settings.upi_id,
            "pn": settings.upi_payee_name,
            "am": amount,
            "cu": "INR",
            "tn": f"Skill Cortex {booking.reference}",
        },
        quote_via=quote,
    )
    return UpiDetails(
        upi_id=settings.upi_id,
        payee_name=settings.upi_payee_name,
        amount_paise=booking.amount_paise,
        booking_reference=booking.reference,
        upi_uri=f"upi://pay?{query}",
    )


def submit_upi_payment(db: Session, user: User, booking_id: UUID, utr: str) -> Booking:
    """Record the learner's UPI payment for admin verification and keep their seat until then."""
    if not get_settings().upi_id:
        raise UpiNotAvailable
    utr = re.sub(r"\s+", "", utr)
    if not UTR_PATTERN.match(utr):
        raise InvalidUtr

    booking = _user_booking(db, user, booking_id, for_update=True)
    if booking.status in (BookingStatus.CONFIRMED, BookingStatus.COMPLETED):
        raise AlreadyPaid
    pending_upi = _pending_upi_payment(db, booking)
    if pending_upi is not None:
        if pending_upi.upi_reference == utr:
            return booking  # the same submission again
        raise UpiAlreadySubmitted
    if db.scalar(select(Payment.id).where(Payment.upi_reference == utr)) is not None:
        raise UtrAlreadyUsed

    now = datetime.now(UTC)
    hold_active = booking.status == BookingStatus.PENDING and booking.expires_at is not None and booking.expires_at > now
    if not hold_active:
        # They may have paid just after the hold ran out. An unswept PENDING hold still has its seat;
        # an EXPIRED one gets the seat back if one is free.
        seat_kept = booking.slot.start_at > now and (
            booking.status == BookingStatus.PENDING
            or (
                booking.status == BookingStatus.EXPIRED
                and not has_other_live_booking(db, booking)
                and hold_seat(db, booking.slot_id)
            )
        )
        if not seat_kept:
            raise BookingNotPayable(
                "Your seat hold has expired and the seat couldn't be kept. If you already paid, contact "
                "info@skillcortexai.com with your UPI transaction ID for a refund."
            )
        booking.status = BookingStatus.PENDING

    # A Razorpay order left open for this booking is superseded (one active payment per booking).
    db.execute(
        update(Payment)
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING)
        .values(status=PaymentStatus.FAILED, failure_reason="Superseded by a UPI payment.")
        .execution_options(synchronize_session="fetch")
    )
    db.add(
        Payment(
            booking=booking,
            method=PaymentMethod.UPI,
            upi_reference=utr,
            amount_paise=booking.amount_paise,
            status=PaymentStatus.PENDING,
        )
    )
    # Hold the seat while an admin verifies (released at session start if never verified).
    booking.expires_at = booking.slot.start_at
    db.flush()
    db.refresh(booking)
    return booking


def confirm_upi_payment(db: Session, payment_id: UUID) -> Payment:
    """Admin checked the money arrived: mark it paid, confirm the booking and notify."""
    payment = _reviewable_payment(db, payment_id)
    booking = db.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
    if booking.status != BookingStatus.PENDING:
        raise UpiPaymentNotReviewable(
            f"This booking is {booking.status.value.lower()}, so it can't be confirmed. Refund the learner via UPI "
            "and reject this payment."
        )
    now = datetime.now(UTC)
    payment.status = PaymentStatus.PAID
    payment.paid_at = now
    booking.status = BookingStatus.CONFIRMED
    booking.confirmed_at = now
    booking.expires_at = None
    db.flush()
    notify_booking_confirmed(db, booking, payment)
    return payment


def reject_upi_payment(db: Session, payment_id: UUID, reason: str) -> Payment:
    """Admin couldn't find the payment: mark it failed and give the learner a short window to fix it."""
    payment = _reviewable_payment(db, payment_id)
    booking = db.scalar(select(Booking).where(Booking.id == payment.booking_id).with_for_update())
    payment.status = PaymentStatus.FAILED
    payment.failure_reason = reason.strip()
    if booking.status == BookingStatus.PENDING:
        booking.expires_at = min(datetime.now(UTC) + RETRY_WINDOW, booking.slot.start_at)
    db.flush()
    return payment


def _pending_upi_payment(db: Session, booking: Booking) -> Payment | None:
    return db.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id,
            Payment.method == PaymentMethod.UPI,
            Payment.status == PaymentStatus.PENDING,
        )
    )


def _user_booking(db: Session, user: User, booking_id: UUID, *, for_update: bool = False) -> Booking:
    query = select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id)
    booking = db.scalar(query.with_for_update() if for_update else query)
    if booking is None:
        raise BookingNotFound
    return booking


def _reviewable_payment(db: Session, payment_id: UUID) -> Payment:
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise PaymentNotFound
    if payment.method != PaymentMethod.UPI or payment.status != PaymentStatus.PENDING:
        raise UpiPaymentNotReviewable
    return payment
