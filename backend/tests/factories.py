"""Minimal model factories for tests. Each helper flushes so ids/defaults are populated."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Booking,
    BookingStatus,
    Department,
    Payment,
    PaymentStatus,
    RecordStatus,
    Slot,
    SlotStatus,
    User,
    UserRole,
    Webinar,
)
from app.utils.security import create_access_token, hash_password

DEFAULT_PASSWORD = "Passw0rd!"


def make_department(db: Session, name: str | None = None, *, status: RecordStatus = RecordStatus.ACTIVE) -> Department:
    department = Department(name=name or f"Dept {uuid.uuid4().hex[:8]}", status=status)
    db.add(department)
    db.flush()
    return department


def make_user(
    db: Session,
    email: str | None = None,
    department: Department | None = None,
    *,
    password: str | None = None,
    role: UserRole = UserRole.USER,
    is_active: bool = True,
) -> User:
    user = User(
        name="Test User",
        email=email or f"user-{uuid.uuid4().hex[:8]}@example.com",
        phone="9876543210",
        password_hash=hash_password(password) if password else "not-a-real-hash",
        department=department,
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def auth_header(user: User) -> dict[str, str]:
    token, _ = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def make_webinar(
    db: Session,
    departments: list[Department] | None = None,
    *,
    title: str = "Python Programming",
    status: RecordStatus = RecordStatus.ACTIVE,
    price_paise: int = 99_900,
) -> Webinar:
    webinar = Webinar(
        title=title,
        description="Learn Python fundamentals and practical programming.",
        instructor="A. Kumar",
        price_paise=price_paise,
        duration_minutes=60,
        status=status,
        departments=departments or [],
    )
    db.add(webinar)
    db.flush()
    return webinar


def make_slot(
    db: Session,
    webinar: Webinar,
    capacity: int = 10,
    *,
    starts_in: timedelta = timedelta(days=7),
    available_seats: int | None = None,
    status: SlotStatus = SlotStatus.ACTIVE,
) -> Slot:
    start = datetime.now(UTC) + starts_in
    slot = Slot(
        webinar=webinar,
        start_at=start,
        end_at=start + timedelta(hours=1),
        capacity=capacity,
        available_seats=capacity if available_seats is None else available_seats,
        status=status,
    )
    db.add(slot)
    db.flush()
    return slot


def make_booking(
    db: Session,
    user: User,
    slot: Slot,
    status: BookingStatus = BookingStatus.PENDING,
    *,
    expires_in: timedelta = timedelta(minutes=15),
) -> Booking:
    """Note: does not touch the slot's seat count."""
    booking = Booking(
        user=user,
        webinar_id=slot.webinar_id,
        slot=slot,
        status=status,
        amount_paise=99_900,
        expires_at=datetime.now(UTC) + expires_in if status == BookingStatus.PENDING else None,
    )
    db.add(booking)
    db.flush()
    return booking


def make_payment(db: Session, booking: Booking, status: PaymentStatus = PaymentStatus.PENDING) -> Payment:
    payment = Payment(
        booking=booking,
        razorpay_order_id=f"order_{uuid.uuid4().hex[:14]}",
        amount_paise=booking.amount_paise,
        status=status,
    )
    db.add(payment)
    db.flush()
    return payment
