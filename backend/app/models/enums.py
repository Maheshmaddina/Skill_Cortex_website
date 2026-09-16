from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Native Postgres enum whose labels are the StrEnum values."""
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class UserRole(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class RecordStatus(StrEnum):
    """Status for departments and webinars (soft delete = INACTIVE)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class SlotStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CANCELLED = "CANCELLED"


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


# Bookings that occupy a seat / block rebooking the same slot.
LIVE_BOOKING_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentMethod(StrEnum):
    RAZORPAY = "RAZORPAY"  # verified automatically (signature / webhook)
    UPI = "UPI"  # direct UPI to the business account; an admin verifies the UTR


class NotificationType(StrEnum):
    REGISTRATION = "REGISTRATION"
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    ADMIN_PAYMENT = "ADMIN_PAYMENT"
    REMINDER = "REMINDER"
    CANCELLATION = "CANCELLATION"
    REFUND = "REFUND"
    PASSWORD_RESET = "PASSWORD_RESET"


class NotificationChannel(StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class RecipientType(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"
