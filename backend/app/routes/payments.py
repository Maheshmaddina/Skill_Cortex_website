from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, DbSession, Gateway, Notifier
from app.schemas.booking import BookingOut
from app.schemas.payment import (
    CheckoutOrder,
    CheckoutPrefill,
    CreateOrderRequest,
    PaymentResult,
    VerifyPaymentRequest,
    WebhookAck,
)
from app.services import payments as payment_service
from app.services import rate_limit
from app.services.payments import OUTCOME_MESSAGES, PaymentOutcome
from app.services.razorpay import PaymentGateway

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/create-order", response_model=CheckoutOrder)
def create_order(payload: CreateOrderRequest, user: CurrentUser, db: DbSession, gateway: Gateway) -> CheckoutOrder:
    """Create (or reuse) the Razorpay order for an unpaid booking and return Checkout options."""
    rate_limit.hit(rate_limit.PAYMENTS_PER_USER, str(user.id))
    session = payment_service.create_checkout_order(db, user, payload.booking_id, gateway)
    db.commit()
    booking, payment = session.booking, session.payment
    return CheckoutOrder(
        key_id=session.key_id,
        order_id=payment.razorpay_order_id,
        amount_paise=payment.amount_paise,
        currency=payment.currency,
        booking_id=booking.id,
        booking_reference=booking.reference,
        webinar_title=booking.webinar.title,
        expires_at=booking.expires_at,
        prefill=CheckoutPrefill(name=user.name, email=user.email, contact=user.phone),
    )


@router.post("/verify", response_model=PaymentResult)
def verify_payment(
    payload: VerifyPaymentRequest,
    user: CurrentUser,
    db: DbSession,
    gateway: Gateway,
    background_tasks: BackgroundTasks,
    notifier: Notifier,
) -> PaymentResult:
    """Called by the frontend with Checkout's handler response. The booking is confirmed only if
    the signature checks out server-side."""
    rate_limit.hit(rate_limit.PAYMENTS_PER_USER, str(user.id))
    outcome, booking = payment_service.verify_checkout_payment(
        db,
        user,
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
        gateway=gateway,
    )
    db.commit()
    background_tasks.add_task(notifier.dispatch_pending)
    db.refresh(booking)
    return PaymentResult(outcome=outcome, message=OUTCOME_MESSAGES[outcome], booking=BookingOut.model_validate(booking))


@router.post("/webhook", response_model=WebhookAck)
async def razorpay_webhook(
    request: Request,
    db: DbSession,
    gateway: Gateway,
    background_tasks: BackgroundTasks,
    notifier: Notifier,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
    x_razorpay_event_id: Annotated[str | None, Header()] = None,
) -> WebhookAck:
    """Razorpay → server notifications (payment.captured, order.paid, payment.failed).

    Needs the raw body for signature verification, so it reads it asynchronously and does the
    database work in a worker thread.
    """
    body = await request.body()
    outcome = await run_in_threadpool(_process_webhook, db, body, x_razorpay_signature, x_razorpay_event_id, gateway)
    background_tasks.add_task(notifier.dispatch_pending)
    return WebhookAck(status=outcome)


def _process_webhook(
    db: Session, body: bytes, signature: str | None, event_id: str | None, gateway: PaymentGateway
) -> PaymentOutcome:
    outcome = payment_service.process_webhook(db, body=body, signature=signature, event_id=event_id, gateway=gateway)
    db.commit()
    return outcome
