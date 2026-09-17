import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole, pg_enum
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.department import Department


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(15))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), default=UserRole.USER, server_default=UserRole.USER.value
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # When the learner last opened their notifications; newer ones count as unread.
    notifications_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Required for learners at registration (enforced in the API); nullable for admins.
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id", ondelete="RESTRICT"))

    department: Mapped[Optional["Department"]] = relationship(back_populates="users")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")


# Case-insensitive email uniqueness.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
