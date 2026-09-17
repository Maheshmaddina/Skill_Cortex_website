from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import NotificationChannel, NotificationStatus, NotificationType, RecipientType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    channel: NotificationChannel
    status: NotificationStatus
    subject: str | None
    message: str
    booking_id: UUID | None
    reminder_offset_days: int | None
    sent_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    count: int


class NotificationAdminOut(NotificationOut):
    user_id: UUID | None
    recipient_type: RecipientType
    recipient_address: str
    attempts: int
    next_attempt_at: datetime | None
    failure_reason: str | None
