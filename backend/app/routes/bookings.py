from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Response, status

from app.dependencies import CurrentUser, DbSession, Notifier, PageParams
from app.models import Booking, BookingStatus
from app.schemas.booking import BookingCreate, BookingOut, SetWebinarCreate
from app.schemas.common import Page
from app.services import bookings as booking_service
from app.services import learner_sessions
from app.services import rate_limit
from app.services.bookings import BookingScope

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingOut,
    responses={200: {"description": "An unexpired unpaid booking for this slot already existed and is returned."}},
)
def create_booking(
    payload: BookingCreate,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    background_tasks: BackgroundTasks,
    notifier: Notifier,
) -> Booking:
    """Hold a seat for 15 minutes while the learner pays. Free webinars are confirmed immediately."""
    rate_limit.hit(rate_limit.BOOKINGS_PER_USER, str(user.id))  # stops one account hoarding seats
    booking, created = booking_service.create_booking(db, user, payload.slot_id)
    db.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    elif booking.status == BookingStatus.CONFIRMED:
        background_tasks.add_task(notifier.dispatch_pending)  # free webinar confirmation
    return booking


@router.post(
    "/set-webinar",
    status_code=status.HTTP_201_CREATED,
    response_model=BookingOut,
    responses={200: {"description": "The learner already held a seat in the session at this time; it is returned."}},
)
def set_webinar(
    payload: SetWebinarCreate,
    user: CurrentUser,
    db: DbSession,
    response: Response,
    background_tasks: BackgroundTasks,
    notifier: Notifier,
) -> Booking:
    """Run the course at the learner's own date and time: creates (or joins) that session and holds their seat.

    Payment and confirmation then work exactly like a normal booking.
    """
    rate_limit.hit(rate_limit.BOOKINGS_PER_USER, str(user.id))
    booking, created = learner_sessions.set_webinar(db, user, **payload.model_dump())
    db.commit()
    if not created:
        response.status_code = status.HTTP_200_OK
    elif booking.status == BookingStatus.CONFIRMED:
        background_tasks.add_task(notifier.dispatch_pending)
    return booking


@router.get("", response_model=Page[BookingOut])
def list_my_bookings(
    user: CurrentUser, db: DbSession, pagination: PageParams, scope: BookingScope | None = None
) -> Page[BookingOut]:
    bookings, total = booking_service.list_user_bookings(
        db, user, scope=scope, offset=pagination.offset, limit=pagination.page_size
    )
    return Page[BookingOut](
        items=[BookingOut.model_validate(b) for b in bookings],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_my_booking(booking_id: UUID, user: CurrentUser, db: DbSession) -> Booking:
    return booking_service.get_user_booking(db, user, booking_id)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_my_booking(booking_id: UUID, user: CurrentUser, db: DbSession) -> Booking:
    """Cancel an unpaid booking and release its seat. Paid bookings can't be cancelled by learners."""
    booking = booking_service.cancel_unpaid_booking(db, user, booking_id)
    db.commit()
    return booking
