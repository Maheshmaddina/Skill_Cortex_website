from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import BookingStatus, PaymentStatus
from app.schemas.booking import BookingOut, BookingUser, BookingWebinar
from app.schemas.slot import SlotAdminOut
from app.services.payments import PaymentOutcome

RazorpayId = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class CreateOrderRequest(BaseModel):
    booking_id: UUID


class CheckoutPrefill(BaseModel):
    name: str
    email: str
    contact: str


class CheckoutOrder(BaseModel):
    """Everything the frontend needs to open Razorpay Checkout."""

    key_id: str
    order_id: str
    amount_paise: int
    currency: str
    booking_id: UUID
    booking_reference: str
    webinar_title: str
    expires_at: datetime | None
    prefill: CheckoutPrefill


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: RazorpayId
    razorpay_payment_id: RazorpayId
    razorpay_signature: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class PaymentResult(BaseModel):
    outcome: PaymentOutcome
    message: str
    booking: BookingOut


class WebhookAck(BaseModel):
    status: PaymentOutcome


class PaymentBooking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    status: BookingStatus
    user: BookingUser
    webinar: BookingWebinar


class PaymentAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount_paise: int
    currency: str
    status: PaymentStatus
    razorpay_order_id: str
    razorpay_payment_id: str | None
    razorpay_refund_id: str | None
    failure_reason: str | None
    paid_at: datetime | None
    refunded_at: datetime | None
    created_at: datetime
    booking: PaymentBooking


class SlotCancellationResult(BaseModel):
    slot: SlotAdminOut
    cancelled_bookings: int
    refunds_issued: int
