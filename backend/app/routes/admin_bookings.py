from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.dependencies import DbSession, Gateway, Notifier, PageParams, require_admin
from app.models import Booking, BookingStatus
from app.schemas.booking import BookingAdminOut
from app.schemas.common import Page
from app.services import bookings as booking_service
from app.services import cancellations

router = APIRouter(prefix="/admin/bookings", tags=["admin: bookings"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[BookingAdminOut])
def list_bookings(
    db: DbSession,
    pagination: PageParams,
    status_filter: Annotated[BookingStatus | None, Query(alias="status")] = None,
    webinar_id: UUID | None = None,
    slot_id: UUID | None = None,
    user_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Booking reference, learner name or email")] = None,
) -> Page[BookingAdminOut]:
    bookings, total = booking_service.list_bookings(
        db,
        status=status_filter,
        webinar_id=webinar_id,
        slot_id=slot_id,
        user_id=user_id,
        q=q,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[BookingAdminOut](
        items=[BookingAdminOut.model_validate(b) for b in bookings],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{booking_id}", response_model=BookingAdminOut)
def get_booking(booking_id: UUID, db: DbSession) -> Booking:
    return booking_service.get_booking(db, booking_id)


@router.post("/{booking_id}/cancel", response_model=BookingAdminOut)
def cancel_booking(
    booking_id: UUID, db: DbSession, gateway: Gateway, background_tasks: BackgroundTasks, notifier: Notifier
) -> Booking:
    """Cancel a pending or confirmed booking; a paid booking is refunded in full and its seat released."""
    cancellations.cancel_booking_as_admin(db, booking_id, gateway)
    db.commit()
    background_tasks.add_task(notifier.dispatch_pending)
    return booking_service.get_booking(db, booking_id)
