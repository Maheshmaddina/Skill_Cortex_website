"""User management for admins (PRD 8.20)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Booking, BookingStatus, Payment, PaymentStatus, User, UserRole
from app.services.auth import revoke_all_refresh_tokens
from app.services.errors import Conflict, NotFound
from app.utils.query import LIKE_ESCAPE, contains_pattern, count_rows


class UserNotFound(NotFound):
    message = "User not found."


class CannotDeactivateSelf(Conflict):
    message = "You can't deactivate your own account."


@dataclass(frozen=True)
class UserSummary:
    user: User
    bookings_count: int
    confirmed_bookings_count: int  # confirmed or attended
    total_paid_paise: int


def list_users(
    db: Session,
    *,
    q: str | None,
    department_id: UUID | None,
    role: UserRole | None,
    is_active: bool | None,
    offset: int,
    limit: int,
) -> tuple[list[UserSummary], int]:
    conditions = []
    if q:
        pattern = contains_pattern(q)
        conditions.append(
            or_(
                User.name.ilike(pattern, escape=LIKE_ESCAPE),
                User.email.ilike(pattern, escape=LIKE_ESCAPE),
                User.phone.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if department_id is not None:
        conditions.append(User.department_id == department_id)
    if role is not None:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active.is_(is_active))

    total = count_rows(db, select(User).where(*conditions))
    rows = db.execute(
        _summary_query().where(*conditions).order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)
    ).all()
    return [UserSummary(*row) for row in rows], total


def get_user_summary(db: Session, user_id: UUID) -> UserSummary:
    row = db.execute(_summary_query().where(User.id == user_id)).first()
    if row is None:
        raise UserNotFound
    return UserSummary(*row)


def set_user_active(db: Session, admin: User, user_id: UUID, is_active: bool) -> UserSummary:
    """Deactivated users can't log in; their sessions end immediately (refresh tokens revoked,
    and access tokens are rejected because the account is inactive). Existing bookings are kept."""
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFound
    if user.id == admin.id and not is_active:
        raise CannotDeactivateSelf
    if user.is_active and not is_active:
        revoke_all_refresh_tokens(db, user.id, datetime.now(UTC))
    user.is_active = is_active
    db.flush()
    return get_user_summary(db, user_id)


def _summary_query() -> Select:
    bookings = (
        select(
            Booking.user_id,
            func.count().label("bookings_count"),
            func.count()
            .filter(Booking.status.in_((BookingStatus.CONFIRMED, BookingStatus.COMPLETED)))
            .label("confirmed_count"),
        )
        .group_by(Booking.user_id)
        .subquery()
    )
    paid = (
        select(Booking.user_id, func.sum(Payment.amount_paise).label("paid_paise"))
        .join(Payment, Payment.booking_id == Booking.id)
        .where(Payment.status == PaymentStatus.PAID)
        .group_by(Booking.user_id)
        .subquery()
    )
    return (
        select(
            User,
            func.coalesce(bookings.c.bookings_count, 0),
            func.coalesce(bookings.c.confirmed_count, 0),
            func.coalesce(paid.c.paid_paise, 0),
        )
        .outerjoin(bookings, bookings.c.user_id == User.id)
        .outerjoin(paid, paid.c.user_id == User.id)
        .options(selectinload(User.department))
    )
