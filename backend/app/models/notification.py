import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Time, text, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RecipientType,
    pg_enum,
)
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "(type = 'REMINDER') = (reminder_offset_days IS NOT NULL)", name="reminder_offset_matches_type"
        ),
        # A reminder row is inserted as a claim before sending, so this blocks duplicates (decision D8).
        Index(
            "uq_notifications_reminder",
            "booking_id",
            "channel",
            "recipient_address",
            "reminder_offset_days",
            unique=True,
            postgresql_where=text("type = 'REMINDER'"),
        ),
        # Confirmation messages go out once per booking/recipient/channel.
        Index(
            "uq_notifications_confirmation",
            "booking_id",
            "type",
            "channel",
            "recipient_address",
            unique=True,
            postgresql_where=text("type IN ('BOOKING_CONFIRMATION', 'ADMIN_PAYMENT')"),
        ),
        # Used by the dispatcher to find due deliveries.
        Index("ix_notifications_status_next_attempt_at", "status", "next_attempt_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id", ondelete="SET NULL"), index=True)
    recipient_type: Mapped[RecipientType] = mapped_column(pg_enum(RecipientType, "recipient_type"))
    recipient_address: Mapped[str] = mapped_column(String(254))
    type: Mapped[NotificationType] = mapped_column(pg_enum(NotificationType, "notification_type"))
    channel: Mapped[NotificationChannel] = mapped_column(pg_enum(NotificationChannel, "notification_channel"))
    subject: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    # Template variables (MSG91 DLT templates need named values, not free text).
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    reminder_offset_days: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReminderRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable reminder schedule: send N days before the slot at a local (IST) time."""

    __tablename__ = "reminder_rules"
    __table_args__ = (CheckConstraint("offset_days >= 0", name="offset_non_negative"),)

    offset_days: Mapped[int] = mapped_column(Integer, unique=True)
    send_time_local: Mapped[time] = mapped_column(Time)
    send_email: Mapped[bool] = mapped_column(default=True, server_default=true())
    send_sms: Mapped[bool] = mapped_column(default=True, server_default=true())
    active: Mapped[bool] = mapped_column(default=True, server_default=true())
