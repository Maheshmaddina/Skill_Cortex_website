import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Sequence, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import BookingStatus, PaymentMethod, PaymentStatus, pg_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.slot import Slot
    from app.models.user import User
    from app.models.webinar import Webinar

# Human-readable booking references: SC-10001, SC-10002, ...
booking_reference_seq = Sequence("booking_reference_seq", start=10001, metadata=Base.metadata)


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_non_negative"),
        # One live booking per user per slot.
        Index(
            "uq_bookings_active_user_slot",
            "user_id",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'CONFIRMED')"),
        ),
        # Used by the hold-expiry job.
        Index("ix_bookings_status_expires_at", "status", "expires_at"),
    )

    reference: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text("'SC-' || nextval('booking_reference_seq')")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    webinar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webinars.id", ondelete="RESTRICT"))
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("slots.id", ondelete="RESTRICT"), index=True)
    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"),
        default=BookingStatus.PENDING,
        server_default=BookingStatus.PENDING.value,
    )
    # Price snapshot at booking time (decision D10).
    amount_paise: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="bookings")
    webinar: Mapped["Webinar"] = relationship()
    slot: Mapped["Slot"] = relationship(back_populates="bookings")
    payments: Mapped[list["Payment"]] = relationship(back_populates="booking")

    @property
    def paid_payment(self) -> "Payment | None":
        """The successful payment, for the receipt."""
        return next((payment for payment in self.payments if payment.status == PaymentStatus.PAID), None)

    @property
    def upi_payment(self) -> "Payment | None":
        """The direct-UPI payment attempt to show: the active one (pending or paid), else the latest."""
        upi = [payment for payment in self.payments if payment.method == PaymentMethod.UPI]
        active = (PaymentStatus.PENDING, PaymentStatus.PAID)
        return max(upi, key=lambda payment: (payment.status in active, payment.created_at)) if upi else None

    @property
    def payment_status(self) -> PaymentStatus | None:
        """The most meaningful status across payment attempts: PAID > REFUNDED > PENDING > FAILED."""
        statuses = {payment.status for payment in self.payments}
        for status in (PaymentStatus.PAID, PaymentStatus.REFUNDED, PaymentStatus.PENDING, PaymentStatus.FAILED):
            if status in statuses:
                return status
        return None
