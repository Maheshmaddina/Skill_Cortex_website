from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RecordStatus, pg_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.slot import Slot

# A webinar can be offered to several departments (decision D1).
webinar_departments = Table(
    "webinar_departments",
    Base.metadata,
    Column("webinar_id", UUID(as_uuid=True), ForeignKey("webinars.id", ondelete="CASCADE"), primary_key=True),
    Column("department_id", UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
)


class Webinar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webinars"
    __table_args__ = (
        CheckConstraint("price_paise >= 0", name="price_non_negative"),
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
    )

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    instructor: Mapped[str | None] = mapped_column(String(120))
    price_paise: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[RecordStatus] = mapped_column(
        pg_enum(RecordStatus, "record_status"), default=RecordStatus.ACTIVE, server_default=RecordStatus.ACTIVE.value
    )

    departments: Mapped[list["Department"]] = relationship(
        secondary=webinar_departments, back_populates="webinars"
    )
    slots: Mapped[list["Slot"]] = relationship(back_populates="webinar")
