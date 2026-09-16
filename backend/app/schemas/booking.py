from datetime import date, datetime, time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import BookingStatus, PaymentStatus


class BookingCreate(BaseModel):
    slot_id: UUID


class SetWebinarCreate(BaseModel):
    """A learner's own date and start time (IST) for a course: on the hour or half hour, 07:00–21:00."""

    webinar_id: UUID
    preferred_date: date
    preferred_time: time
    note: Annotated[str | None, Field(max_length=500)] = None


class BookingWebinar(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    duration_minutes: int


class BookingSlot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    start_at: datetime
    end_at: datetime


class BookingUpiPayment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    upi_reference: str
    status: PaymentStatus
    failure_reason: str | None
    created_at: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    status: BookingStatus
    payment_status: PaymentStatus | None
    amount_paise: int
    expires_at: datetime | None  # payment deadline while PENDING
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    webinar: BookingWebinar
    slot: BookingSlot
    upi_payment: BookingUpiPayment | None = None  # latest direct-UPI attempt, if any


class BookingUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone: str


class BookingAdminOut(BookingOut):
    user: BookingUser
    updated_at: datetime
