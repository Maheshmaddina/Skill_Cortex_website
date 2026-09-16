from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.dependencies import DbSession, Notifier, PageParams, require_admin
from app.models import Payment, PaymentMethod, PaymentStatus
from app.schemas.common import Page
from app.schemas.payment import PaymentAdminOut, RejectUpiPaymentRequest
from app.services import payments as payment_service
from app.services import upi_payments

router = APIRouter(prefix="/admin/payments", tags=["admin: payments"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[PaymentAdminOut])
def list_payments(
    db: DbSession,
    pagination: PageParams,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    booking_id: UUID | None = None,
    user_id: UUID | None = None,
    method: PaymentMethod | None = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Razorpay order/payment id, booking reference, learner name/email")
    ] = None,
) -> Page[PaymentAdminOut]:
    payments, total = payment_service.list_payments(
        db,
        status=status_filter,
        booking_id=booking_id,
        user_id=user_id,
        method=method,
        q=q,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[PaymentAdminOut](
        items=[PaymentAdminOut.model_validate(p) for p in payments],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{payment_id}", response_model=PaymentAdminOut)
def get_payment(payment_id: UUID, db: DbSession) -> Payment:
    return payment_service.get_payment(db, payment_id)


@router.post("/{payment_id}/confirm-upi", response_model=PaymentAdminOut)
def confirm_upi_payment(payment_id: UUID, db: DbSession, background_tasks: BackgroundTasks, notifier: Notifier) -> Payment:
    """You found this UPI payment in the bank/UPI account: confirm the booking and notify the learner."""
    upi_payments.confirm_upi_payment(db, payment_id)
    db.commit()
    background_tasks.add_task(notifier.dispatch_pending)
    return payment_service.get_payment(db, payment_id)


@router.post("/{payment_id}/reject-upi", response_model=PaymentAdminOut)
def reject_upi_payment(payment_id: UUID, payload: RejectUpiPaymentRequest, db: DbSession) -> Payment:
    """The UPI payment wasn't received: mark it failed; the learner gets 30 minutes to correct the UTR."""
    upi_payments.reject_upi_payment(db, payment_id, payload.reason)
    db.commit()
    return payment_service.get_payment(db, payment_id)
