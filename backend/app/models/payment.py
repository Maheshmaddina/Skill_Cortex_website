import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import PaymentMethod, PaymentStatus, pg_enum
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_non_negative"),
        CheckConstraint("(method = 'RAZORPAY') = (razorpay_order_id IS NOT NULL)", name="razorpay_order_matches_method"),
        CheckConstraint("(method = 'UPI') = (upi_reference IS NOT NULL)", name="upi_reference_matches_method"),
        # At most one in-flight or successful payment per booking; retries allowed after FAILED.
        Index(
            "uq_payments_active_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'PAID')"),
        ),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id", ondelete="RESTRICT"), index=True)
    method: Mapped[PaymentMethod] = mapped_column(
        pg_enum(PaymentMethod, "payment_method"),
        default=PaymentMethod.RAZORPAY,
        server_default=PaymentMethod.RAZORPAY.value,
    )
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    # UPI transaction reference (UTR / RRN) the learner entered after paying by UPI.
    upi_reference: Mapped[str | None] = mapped_column(String(32), unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    razorpay_signature: Mapped[str | None] = mapped_column(String(256))
    amount_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    razorpay_refund_id: Mapped[str | None] = mapped_column(String(64))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    booking: Mapped["Booking"] = relationship(back_populates="payments")


class PaymentEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Raw Razorpay webhook deliveries, kept for audit and idempotency (decision D5)."""

    __tablename__ = "payment_events"

    razorpay_event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    signature_valid: Mapped[bool] = mapped_column(Boolean)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
