"""Admin dashboard figures (PRD FR-14, 8.19)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingStatus,
    Notification,
    NotificationStatus,
    Payment,
    PaymentStatus,
    RecordStatus,
    Slot,
    SlotStatus,
    User,
    UserRole,
    Webinar,
)

UPCOMING_SESSIONS_SHOWN = 5
RECENT_WINDOW = timedelta(days=30)


def dashboard_stats(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """Revenue counts PAID payments only; refunded payments are excluded."""
    now = now or datetime.now(UTC)
    recent = now - RECENT_WINDOW

    def scalar(query) -> int:
        return db.scalar(query) or 0

    def count(model, *conditions) -> int:
        return scalar(select(func.count()).select_from(model).where(*conditions))

    bookings_by_status = dict(db.execute(select(Booking.status, func.count()).group_by(Booking.status)).all())
    payments_by_status = dict(db.execute(select(Payment.status, func.count()).group_by(Payment.status)).all())
    paid_total = select(func.sum(Payment.amount_paise)).where(Payment.status == PaymentStatus.PAID)

    return {
        "generated_at": now,
        "users": {
            "learners": count(User, User.role == UserRole.USER),
            "new_learners_last_30_days": count(User, User.role == UserRole.USER, User.created_at >= recent),
            "admins": count(User, User.role == UserRole.ADMIN),
        },
        "webinars": {
            "total": count(Webinar),
            "active": count(Webinar, Webinar.status == RecordStatus.ACTIVE),
        },
        "upcoming_sessions_count": count(Slot, Slot.status == SlotStatus.ACTIVE, Slot.start_at > now),
        "upcoming_learner_set_sessions_count": count(
            Slot, Slot.status == SlotStatus.ACTIVE, Slot.start_at > now, Slot.set_by_user_id.is_not(None)
        ),
        "bookings": {
            "total": sum(bookings_by_status.values()),
            **{status.value.lower(): bookings_by_status.get(status, 0) for status in BookingStatus},
        },
        "payments": {
            "successful": payments_by_status.get(PaymentStatus.PAID, 0),
            "pending": payments_by_status.get(PaymentStatus.PENDING, 0),
            "failed": payments_by_status.get(PaymentStatus.FAILED, 0),
            "refunded": payments_by_status.get(PaymentStatus.REFUNDED, 0),
        },
        "revenue": {
            "total_paise": scalar(paid_total),
            "last_30_days_paise": scalar(paid_total.where(Payment.paid_at >= recent)),
        },
        "notifications": {
            "pending": count(Notification, Notification.status == NotificationStatus.PENDING),
            "failed": count(Notification, Notification.status == NotificationStatus.FAILED),
        },
        "upcoming_sessions": _upcoming_sessions(db, now),
    }


def _upcoming_sessions(db: Session, now: datetime) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Slot, Webinar.title)
        .join(Slot.webinar)
        .where(Slot.status == SlotStatus.ACTIVE, Slot.start_at > now)
        .order_by(Slot.start_at, Slot.id)
        .limit(UPCOMING_SESSIONS_SHOWN)
    ).all()
    return [
        {
            "slot_id": slot.id,
            "webinar_id": slot.webinar_id,
            "webinar_title": title,
            "start_at": slot.start_at,
            "end_at": slot.end_at,
            "capacity": slot.capacity,
            "booked_seats": slot.capacity - slot.available_seats,
            "available_seats": slot.available_seats,
            "set_by_learner": slot.set_by_user_id is not None,
        }
        for slot, title in rows
    ]
