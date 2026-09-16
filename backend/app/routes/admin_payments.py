from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import DbSession, PageParams, require_admin
from app.models import Payment, PaymentStatus
from app.schemas.common import Page
from app.schemas.payment import PaymentAdminOut
from app.services import payments as payment_service

router = APIRouter(prefix="/admin/payments", tags=["admin: payments"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[PaymentAdminOut])
def list_payments(
    db: DbSession,
    pagination: PageParams,
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    booking_id: UUID | None = None,
    user_id: UUID | None = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Razorpay order/payment id, booking reference, learner name/email")
    ] = None,
) -> Page[PaymentAdminOut]:
    payments, total = payment_service.list_payments(
        db,
        status=status_filter,
        booking_id=booking_id,
        user_id=user_id,
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
