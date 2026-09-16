from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.dependencies import DbSession, Gateway, Notifier, PageParams, require_admin
from app.models import Slot, SlotStatus
from app.schemas.common import Page
from app.schemas.payment import SlotCancellationResult
from app.schemas.slot import SlotAdminOut, SlotCreate, SlotUpdate
from app.services import cancellations
from app.services import slots as slot_service

router = APIRouter(prefix="/admin/slots", tags=["admin: slots"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[SlotAdminOut])
def list_slots(
    db: DbSession,
    pagination: PageParams,
    webinar_id: UUID | None = None,
    upcoming: bool = True,
    learner_set: bool | None = None,
) -> Page[SlotAdminOut]:
    """`learner_set=true`: only sessions learners set for their own date and time."""
    slots, total = slot_service.list_slots(
        db,
        webinar_id=webinar_id,
        upcoming_only=upcoming,
        learner_set=learner_set,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[SlotAdminOut](
        items=[SlotAdminOut.model_validate(s) for s in slots],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SlotAdminOut)
def create_slot(payload: SlotCreate, db: DbSession) -> Slot:
    slot = slot_service.create_slot(db, **payload.model_dump())
    db.commit()
    return slot


@router.get("/{slot_id}", response_model=SlotAdminOut)
def get_slot(slot_id: UUID, db: DbSession) -> Slot:
    return slot_service.get_slot(db, slot_id)


@router.put("/{slot_id}", response_model=SlotAdminOut)
def update_slot(slot_id: UUID, payload: SlotUpdate, db: DbSession) -> Slot:
    slot = slot_service.update_slot(db, slot_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return slot


@router.delete("/{slot_id}", response_model=SlotAdminOut)
def deactivate_slot(slot_id: UUID, db: DbSession) -> Slot:
    """Soft delete. Refused while the slot has pending or confirmed bookings (use /cancel instead)."""
    slot = slot_service.update_slot(db, slot_id, {"status": SlotStatus.INACTIVE})
    db.commit()
    return slot


@router.post("/{slot_id}/cancel", response_model=SlotCancellationResult)
def cancel_slot(
    slot_id: UUID, db: DbSession, gateway: Gateway, background_tasks: BackgroundTasks, notifier: Notifier
) -> SlotCancellationResult:
    """Cancel the session: stop new bookings, cancel every live booking and refund paid ones.

    Each booking is committed separately because refunds can't be rolled back; if a refund
    fails, calling this again picks up the bookings that remain.
    """
    booking_ids = cancellations.begin_slot_cancellation(db, slot_id)
    db.commit()

    refunds = 0
    for booking_id in booking_ids:
        _, refunded = cancellations.cancel_booking_as_admin(db, booking_id, gateway)
        db.commit()
        refunds += refunded

    background_tasks.add_task(notifier.dispatch_pending)
    slot = slot_service.get_slot(db, slot_id)
    db.refresh(slot)
    return SlotCancellationResult(
        slot=SlotAdminOut.model_validate(slot), cancelled_bookings=len(booking_ids), refunds_issued=refunds
    )
