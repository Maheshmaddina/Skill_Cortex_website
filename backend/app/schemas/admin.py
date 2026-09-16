from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models import UserRole
from app.schemas.department import DepartmentOut
from app.services.admin_users import UserSummary


# --- dashboard -----------------------------------------------------------------


class UserStats(BaseModel):
    learners: int
    new_learners_last_30_days: int
    admins: int


class WebinarStats(BaseModel):
    total: int
    active: int


class BookingStats(BaseModel):
    total: int
    pending: int
    confirmed: int
    expired: int
    failed: int
    cancelled: int
    completed: int


class PaymentStats(BaseModel):
    successful: int
    pending: int
    failed: int
    refunded: int
    upi_awaiting_verification: int


class RevenueStats(BaseModel):
    total_paise: int
    last_30_days_paise: int


class NotificationStats(BaseModel):
    pending: int
    failed: int


class UpcomingSession(BaseModel):
    slot_id: UUID
    webinar_id: UUID
    webinar_title: str
    start_at: datetime
    end_at: datetime
    capacity: int
    booked_seats: int
    available_seats: int
    set_by_learner: bool


class DashboardStats(BaseModel):
    generated_at: datetime
    users: UserStats
    webinars: WebinarStats
    upcoming_sessions_count: int
    upcoming_learner_set_sessions_count: int
    bookings: BookingStats
    payments: PaymentStats
    revenue: RevenueStats
    notifications: NotificationStats
    upcoming_sessions: list[UpcomingSession]


# --- users ---------------------------------------------------------------------


class AdminUserOut(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    role: UserRole
    is_active: bool
    department: DepartmentOut | None
    created_at: datetime
    bookings_count: int
    confirmed_bookings_count: int
    total_paid_paise: int

    @classmethod
    def from_summary(cls, summary: UserSummary) -> "AdminUserOut":
        user = summary.user
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
            department=DepartmentOut.model_validate(user.department) if user.department else None,
            created_at=user.created_at,
            bookings_count=summary.bookings_count,
            confirmed_bookings_count=summary.confirmed_bookings_count,
            total_paid_paise=summary.total_paid_paise,
        )


class AdminUserUpdate(BaseModel):
    is_active: bool
