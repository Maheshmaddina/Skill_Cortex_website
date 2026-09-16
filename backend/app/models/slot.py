import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import SlotStatus, pg_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User
    from app.models.webinar import Webinar


class Slot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "slots"
    __table_args__ = (
        CheckConstraint("end_at > start_at", name="end_after_start"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        # Last line of defence against overbooking (decision D4).
        CheckConstraint("available_seats >= 0 AND available_seats <= capacity", name="seats_within_capacity"),
        Index("ix_slots_webinar_id_start_at", "webinar_id", "start_at"),
    )

    webinar_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webinars.id", ondelete="RESTRICT"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer)
    available_seats: Mapped[int] = mapped_column(Integer)
    status: Mapped[SlotStatus] = mapped_column(
        pg_enum(SlotStatus, "slot_status"), default=SlotStatus.ACTIVE, server_default=SlotStatus.ACTIVE.value
    )

    # Set when a learner picked this date and time themselves ("Set webinar"); null for admin-published slots.
    set_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    learner_note: Mapped[str | None] = mapped_column(String(500))

    webinar: Mapped["Webinar"] = relationship(back_populates="slots")
    set_by: Mapped["User | None"] = relationship()
    bookings: Mapped[list["Booking"]] = relationship(back_populates="slot")
