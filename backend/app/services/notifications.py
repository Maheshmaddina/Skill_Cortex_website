"""Notification outbox and dispatcher (PRD 8.14–8.16, 8.25, §19; decision D12).

Events call `notify_*` inside their own transaction, which inserts PENDING rows — so a
committed payment always has its notifications recorded. Delivery happens afterwards:
right after the response (FastAPI background task) and every minute from the scheduler,
which also retries failures. A delivery failure only ever changes the notification row.

Password-reset emails are the exception: the link is never stored, so they are delivered
once, directly, and the stored row carries a redacted message.
"""

import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    Payment,
    RecipientType,
    User,
)
from app.services import notification_messages as messages
from app.services.errors import Conflict, NotFound
from app.services.notification_messages import RenderedMessage
from app.services.notification_providers import NotificationProviders, get_notification_providers
from app.utils.query import LIKE_ESCAPE, contains_pattern, count_rows

logger = logging.getLogger("uvicorn.error")

RETRY_DELAY = timedelta(minutes=5)
REDACTED_RESET_MESSAGE = "Password reset link sent. The link itself is not stored."


class NotificationNotFound(NotFound):
    message = "Notification not found."


class NotificationNotRetryable(Conflict):
    message = "This notification can't be resent."


# --- enqueueing (called inside the triggering transaction) ---------------------


def notify_registration(db: Session, user: User) -> None:
    message = messages.registration(user)
    _enqueue(db, [_row(NotificationType.REGISTRATION, NotificationChannel.EMAIL, user.email, message, user=user)])


def notify_booking_confirmed(db: Session, booking: Booking, payment: Payment | None = None) -> None:
    """Learner email + SMS; for a paid booking, admin email + SMS as well. Safe to call twice."""
    rows = _learner_rows(NotificationType.BOOKING_CONFIRMATION, booking, messages.booking_confirmed(booking, payment))
    if payment is not None:
        rows += _admin_rows(NotificationType.ADMIN_PAYMENT, booking, messages.admin_payment(booking, payment))
    _enqueue(db, rows)


def notify_booking_cancelled(db: Session, booking: Booking, *, refunded: bool) -> None:
    _enqueue(
        db, _learner_rows(NotificationType.CANCELLATION, booking, messages.booking_cancelled(booking, refunded=refunded))
    )


def notify_payment_refunded(db: Session, booking: Booking, payment: Payment) -> None:
    _enqueue(db, _learner_rows(NotificationType.REFUND, booking, messages.payment_refunded(booking, payment)))


def notify_reminder(db: Session, booking: Booking, *, offset_days: int, email: bool, sms: bool) -> int:
    """Queue a reminder; returns how many rows were new (0 if this reminder was already queued)."""
    message = messages.reminder(booking, offset_days)
    user = booking.user
    rows = []
    if email:
        rows.append(_row(NotificationType.REMINDER, NotificationChannel.EMAIL, user.email, message, user=user, booking=booking, reminder_offset_days=offset_days))
    if sms:
        rows.append(_row(NotificationType.REMINDER, NotificationChannel.SMS, user.phone, message, user=user, booking=booking, reminder_offset_days=offset_days))
    return _enqueue(db, rows)


def record_password_reset(db: Session, user: User) -> Notification:
    notification = Notification(
        user_id=user.id,
        recipient_type=RecipientType.USER,
        recipient_address=user.email,
        type=NotificationType.PASSWORD_RESET,
        channel=NotificationChannel.EMAIL,
        subject=messages.password_reset(user.name, "").subject,
        message=REDACTED_RESET_MESSAGE,
    )
    db.add(notification)
    db.flush()
    return notification


def _learner_rows(type_: NotificationType, booking: Booking, message: RenderedMessage) -> list[dict[str, Any]]:
    user = booking.user
    return [
        _row(type_, NotificationChannel.EMAIL, user.email, message, user=user, booking=booking),
        _row(type_, NotificationChannel.SMS, user.phone, message, user=user, booking=booking),
    ]


def _admin_rows(type_: NotificationType, booking: Booking, message: RenderedMessage) -> list[dict[str, Any]]:
    settings = get_settings()
    return [
        *(_row(type_, NotificationChannel.EMAIL, email, message, booking=booking) for email in settings.admin_notify_email_list),
        *(_row(type_, NotificationChannel.SMS, phone, message, booking=booking) for phone in settings.admin_notify_phone_list),
    ]


def _row(
    type_: NotificationType,
    channel: NotificationChannel,
    address: str,
    message: RenderedMessage,
    *,
    user: User | None = None,
    booking: Booking | None = None,
    reminder_offset_days: int | None = None,
) -> dict[str, Any]:
    is_email = channel == NotificationChannel.EMAIL
    return {
        "user_id": user.id if user else None,
        "booking_id": booking.id if booking else None,
        "recipient_type": RecipientType.USER if user else RecipientType.ADMIN,
        "recipient_address": address,
        "type": type_,
        "channel": channel,
        "subject": message.subject if is_email else None,
        "message": message.email_text if is_email else message.sms_text,
        "payload": message.variables or None,
        "reminder_offset_days": reminder_offset_days,
    }


def _enqueue(db: Session, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    # The partial unique indexes make repeated confirmations and reminders a no-op.
    # Count RETURNING rows: the driver reports rowcount -1 for this multi-row insert.
    inserted = db.execute(insert(Notification).values(rows).on_conflict_do_nothing().returning(Notification.id))
    return len(inserted.all())


# --- delivery ------------------------------------------------------------------


def dispatch_pending(
    db: Session, providers: NotificationProviders, *, now: datetime | None = None, limit: int = 50
) -> int:
    """Deliver due PENDING notifications, committing after each one. Returns how many were sent.

    Rows are claimed with FOR UPDATE SKIP LOCKED, so concurrent dispatchers don't double-send.
    """
    now = now or datetime.now(UTC)
    candidate_ids = db.scalars(
        select(Notification.id).where(_is_due(now)).order_by(Notification.created_at, Notification.id).limit(limit)
    ).all()
    delivered = 0
    for notification_id in candidate_ids:
        notification = db.scalar(
            select(Notification)
            .where(Notification.id == notification_id, _is_due(now))
            .with_for_update(skip_locked=True)
        )
        if notification is None:
            continue
        if notification.type == NotificationType.REMINDER and not _booking_still_confirmed(db, notification):
            # Cancelled after the reminder was queued: reminders go only to confirmed bookings (BR-08).
            notification.status = NotificationStatus.FAILED
            notification.failure_reason = "Booking is no longer confirmed."
            notification.next_attempt_at = None
        else:
            delivered += _attempt(notification, providers, now)
        db.commit()
    return delivered


def _booking_still_confirmed(db: Session, notification: Notification) -> bool:
    booking = db.get(Booking, notification.booking_id) if notification.booking_id else None
    return booking is not None and booking.status == BookingStatus.CONFIRMED


def deliver_password_reset(
    db: Session, providers: NotificationProviders, notification_id: UUID, link: str
) -> bool:
    notification = db.scalar(select(Notification).where(Notification.id == notification_id).with_for_update())
    if notification is None or notification.status != NotificationStatus.PENDING:
        return False
    user = db.get(User, notification.user_id)
    message = messages.password_reset(user.name if user else "there", link)
    sent = _attempt(notification, providers, datetime.now(UTC), one_shot_text=message.email_text)
    db.commit()
    return sent


def _is_due(now: datetime):
    return and_(
        Notification.status == NotificationStatus.PENDING,
        Notification.type != NotificationType.PASSWORD_RESET,
        or_(Notification.next_attempt_at.is_(None), Notification.next_attempt_at <= now),
    )


def _attempt(
    notification: Notification, providers: NotificationProviders, now: datetime, *, one_shot_text: str | None = None
) -> bool:
    notification.attempts += 1
    try:
        if notification.channel == NotificationChannel.EMAIL:
            providers.email.send(
                to=notification.recipient_address,
                subject=notification.subject or "Skill Cortex",
                text=one_shot_text or notification.message,
            )
        else:
            providers.sms.send(
                to=notification.recipient_address,
                text=notification.message,
                template_key=notification.type.value,
                variables=notification.payload or {},
            )
    except Exception as exc:  # any provider failure must stay contained (PRD §19)
        logger.warning("Notification %s (%s/%s) failed: %s", notification.id, notification.type, notification.channel, exc)
        notification.failure_reason = (str(exc) or exc.__class__.__name__)[:500]
        if one_shot_text is not None or notification.attempts >= get_settings().notification_max_attempts:
            notification.status = NotificationStatus.FAILED
            notification.next_attempt_at = None
        else:
            notification.next_attempt_at = now + RETRY_DELAY * notification.attempts
        return False

    notification.status = NotificationStatus.SENT
    notification.sent_at = now
    notification.failure_reason = None
    notification.next_attempt_at = None
    return True


class NotificationDispatcher:
    """Delivery entry points for background tasks and the scheduler (own session each call)."""

    def dispatch_pending(self) -> None:
        try:
            with SessionLocal() as db:
                dispatch_pending(db, get_notification_providers())
        except Exception:
            logger.exception("Notification dispatch failed")

    def deliver_password_reset(self, notification_id: UUID, link: str) -> None:
        try:
            with SessionLocal() as db:
                deliver_password_reset(db, get_notification_providers(), notification_id, link)
        except Exception:
            logger.exception("Password reset delivery failed")


@lru_cache
def get_notification_dispatcher() -> NotificationDispatcher:
    return NotificationDispatcher()


# --- queries & admin actions ---------------------------------------------------


def list_notifications(
    db: Session,
    *,
    user_id: UUID | None = None,
    status: NotificationStatus | None = None,
    type_: NotificationType | None = None,
    channel: NotificationChannel | None = None,
    booking_id: UUID | None = None,
    q: str | None = None,
    offset: int,
    limit: int,
) -> tuple[list[Notification], int]:
    query = select(Notification)
    for column, value in (
        (Notification.user_id, user_id),
        (Notification.status, status),
        (Notification.type, type_),
        (Notification.channel, channel),
        (Notification.booking_id, booking_id),
    ):
        if value is not None:
            query = query.where(column == value)
    if q:
        pattern = contains_pattern(q)
        query = query.where(
            or_(
                Notification.recipient_address.ilike(pattern, escape=LIKE_ESCAPE),
                Notification.subject.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    total = count_rows(db, query)
    rows = db.scalars(query.order_by(Notification.created_at.desc(), Notification.id).offset(offset).limit(limit)).all()
    return list(rows), total


def get_notification(db: Session, notification_id: UUID) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise NotificationNotFound
    return notification


def retry_notification(db: Session, notification_id: UUID) -> Notification:
    notification = get_notification(db, notification_id)
    if notification.type == NotificationType.PASSWORD_RESET:
        raise NotificationNotRetryable("Password reset emails can't be resent. Ask the user to request a new link.")
    if notification.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED):
        raise NotificationNotRetryable("This notification has already been sent.")
    notification.status = NotificationStatus.PENDING
    notification.attempts = 0
    notification.next_attempt_at = None
    notification.failure_reason = None
    db.flush()
    return notification
