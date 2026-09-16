"""Slot management (PRD 8.22). Seat accounting: booked seats = capacity − available_seats,
which includes unexpired PENDING holds (decision D4)."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.models import LIVE_BOOKING_STATUSES, Booking, Slot, SlotStatus
from app.services.errors import Conflict, NotFound, ServiceError
from app.services.webinars import get_webinar
from app.utils.query import count_rows


class SlotNotFound(NotFound):
    message = "Slot not found."


class InvalidSlot(ServiceError):
    message = "Invalid slot."


class SlotHasBookings(Conflict):
    message = "This slot has active bookings."


def get_slot(db: Session, slot_id: UUID, *, for_update: bool = False) -> Slot:
    query = select(Slot).where(Slot.id == slot_id)
    if for_update:
        query = query.with_for_update()
    slot = db.scalar(query)
    if slot is None:
        raise SlotNotFound
    return slot


def list_slots(
    db: Session,
    *,
    webinar_id: UUID | None,
    upcoming_only: bool,
    learner_set: bool | None = None,
    offset: int,
    limit: int,
) -> tuple[list[Slot], int]:
    query = select(Slot)
    if webinar_id is not None:
        query = query.where(Slot.webinar_id == webinar_id)
    if learner_set is not None:
        query = query.where(Slot.set_by_user_id.is_not(None) if learner_set else Slot.set_by_user_id.is_(None))
    if upcoming_only:
        query = query.where(Slot.start_at > datetime.now(UTC))
    total = count_rows(db, query)
    slots = db.scalars(
        query.options(selectinload(Slot.set_by), selectinload(Slot.webinar)).order_by(Slot.start_at, Slot.id).offset(offset).limit(limit)
    ).all()
    return list(slots), total


def create_slot(db: Session, *, webinar_id: UUID, start_at: datetime, end_at: datetime, capacity: int) -> Slot:
    webinar = get_webinar(db, webinar_id)
    _validate_times(start_at, end_at)
    slot = Slot(webinar=webinar, start_at=start_at, end_at=end_at, capacity=capacity, available_seats=capacity)
    db.add(slot)
    db.flush()
    return slot


def update_slot(db: Session, slot_id: UUID, changes: dict[str, Any]) -> Slot:
    """Apply a partial update under a row lock, so it can't interleave with seat holds.

    Rescheduling or deactivating a slot with live bookings is refused (decision D7:
    those bookings must be cancelled/refunded first).
    """
    slot = get_slot(db, slot_id, for_update=True)
    live = has_live_bookings(db, slot.id)

    new_start = changes.get("start_at", slot.start_at)
    new_end = changes.get("end_at", slot.end_at)
    if (new_start, new_end) != (slot.start_at, slot.end_at):
        if live:
            raise SlotHasBookings("This slot has active bookings, so its time can't be changed.")
        _validate_times(new_start, new_end)
        slot.start_at, slot.end_at = new_start, new_end

    if "capacity" in changes:
        booked = slot.capacity - slot.available_seats
        if changes["capacity"] < booked:
            raise SlotHasBookings(f"Capacity can't be lower than the {booked} seats already booked.")
        slot.capacity = changes["capacity"]
        slot.available_seats = changes["capacity"] - booked

    new_status = changes.get("status", slot.status)
    if new_status != slot.status:
        if new_status != SlotStatus.ACTIVE and live:
            raise SlotHasBookings("This slot has active bookings. Cancel them before deactivating it.")
        slot.status = new_status

    db.flush()
    return slot


def has_live_bookings(db: Session, slot_id: UUID) -> bool:
    return bool(
        db.scalar(select(exists().where(Booking.slot_id == slot_id, Booking.status.in_(LIVE_BOOKING_STATUSES))))
    )


def _validate_times(start_at: datetime, end_at: datetime) -> None:
    if start_at <= datetime.now(UTC):
        raise InvalidSlot("Slot must start in the future.")
    if end_at <= start_at:
        raise InvalidSlot("End time must be after start time.")
