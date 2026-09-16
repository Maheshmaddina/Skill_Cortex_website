"""Import every model so Base.metadata is complete (Alembic, tests)."""

from app.models.auth_token import PasswordResetToken, RefreshToken
from app.models.booking import Booking, booking_reference_seq
from app.models.department import Department
from app.models.enums import (
    LIVE_BOOKING_STATUSES,
    BookingStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PaymentMethod,
    PaymentStatus,
    RecipientType,
    RecordStatus,
    SlotStatus,
    UserRole,
)
from app.models.notification import Notification, ReminderRule
from app.models.payment import Payment, PaymentEvent
from app.models.rate_limit import RateLimitCounter
from app.models.slot import Slot
from app.models.user import User
from app.models.webinar import Webinar, webinar_departments

__all__ = [
    "LIVE_BOOKING_STATUSES",
    "Booking",
    "BookingStatus",
    "Department",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "NotificationType",
    "PasswordResetToken",
    "Payment",
    "PaymentEvent",
    "PaymentMethod",
    "PaymentStatus",
    "RateLimitCounter",
    "RecipientType",
    "RecordStatus",
    "RefreshToken",
    "ReminderRule",
    "Slot",
    "SlotStatus",
    "User",
    "UserRole",
    "Webinar",
    "booking_reference_seq",
    "webinar_departments",
]
