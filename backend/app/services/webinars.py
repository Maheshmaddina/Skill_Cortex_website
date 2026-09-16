"""Webinar management (admin) and the public catalog (PRD 8.6–8.7, 8.21)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Department, RecordStatus, Slot, SlotStatus, Webinar
from app.services.departments import DepartmentNotAvailable
from app.services.errors import NotFound
from app.utils.query import contains_pattern, count_rows


class WebinarNotFound(NotFound):
    message = "Webinar not found."


class WebinarUnavailable(NotFound):
    message = "This webinar is currently unavailable."


@dataclass(frozen=True)
class CatalogEntry:
    webinar: Webinar
    bookable_slots: list[Slot]  # upcoming ACTIVE slots, soonest first (full ones included)

    @property
    def departments(self) -> list[Department]:
        return [d for d in self.webinar.departments if d.status == RecordStatus.ACTIVE]

    @property
    def next_available_slot(self) -> Slot | None:
        return next((slot for slot in self.bookable_slots if slot.available_seats > 0), None)

    @property
    def available_seats(self) -> int:
        return sum(slot.available_seats for slot in self.bookable_slots)


# --- admin ---------------------------------------------------------------------


def get_webinar(db: Session, webinar_id: UUID) -> Webinar:
    webinar = db.get(Webinar, webinar_id)
    if webinar is None:
        raise WebinarNotFound
    return webinar


def list_webinars(
    db: Session,
    *,
    status: RecordStatus | None,
    department_id: UUID | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Webinar], int]:
    query = _filtered(select(Webinar), status=status, department_id=department_id, q=q)
    total = count_rows(db, query)
    webinars = db.scalars(
        query.options(selectinload(Webinar.departments)).order_by(Webinar.title, Webinar.id).offset(offset).limit(limit)
    ).all()
    return list(webinars), total


def create_webinar(
    db: Session,
    *,
    title: str,
    description: str,
    instructor: str | None,
    price_paise: int,
    duration_minutes: int,
    department_ids: list[UUID],
    status: RecordStatus,
) -> Webinar:
    webinar = Webinar(
        title=title,
        description=description,
        instructor=instructor,
        price_paise=price_paise,
        duration_minutes=duration_minutes,
        status=status,
        departments=_resolve_active_departments(db, department_ids),
    )
    db.add(webinar)
    db.flush()
    return webinar


def update_webinar(db: Session, webinar_id: UUID, changes: dict[str, Any]) -> Webinar:
    """Apply a partial update. Deactivation is `{"status": INACTIVE}` (soft delete);
    existing bookings stay valid, but the webinar leaves the catalog and can't be booked."""
    webinar = get_webinar(db, webinar_id)
    changes = dict(changes)
    if "department_ids" in changes:
        webinar.departments = _resolve_active_departments(db, changes.pop("department_ids"))
    for field, value in changes.items():
        setattr(webinar, field, value)
    db.flush()
    return webinar


def _resolve_active_departments(db: Session, department_ids: list[UUID]) -> list[Department]:
    unique_ids = list(dict.fromkeys(department_ids))
    found = db.scalars(
        select(Department).where(Department.id.in_(unique_ids), Department.status == RecordStatus.ACTIVE)
    ).all()
    by_id = {department.id: department for department in found}
    missing = [str(department_id) for department_id in unique_ids if department_id not in by_id]
    if missing:
        raise DepartmentNotAvailable(f"These departments are not available: {', '.join(missing)}")
    return [by_id[department_id] for department_id in unique_ids]


# --- public catalog ------------------------------------------------------------


def list_catalog(
    db: Session, *, department_id: UUID | None, q: str | None, offset: int, limit: int
) -> tuple[list[CatalogEntry], int]:
    """Active webinars, soonest bookable slot first; webinars with no open slot come last."""
    now = datetime.now(UTC)
    query = _filtered(
        select(Webinar), status=RecordStatus.ACTIVE, department_id=department_id, q=q, active_department_only=True
    )
    total = count_rows(db, query)

    next_open_start = (
        select(func.min(Slot.start_at))
        .where(Slot.webinar_id == Webinar.id, *_bookable(now), Slot.available_seats > 0)
        .correlate(Webinar)
        .scalar_subquery()
    )
    webinars = db.scalars(
        query.options(selectinload(Webinar.departments))
        .order_by(next_open_start.asc().nulls_last(), Webinar.title, Webinar.id)
        .offset(offset)
        .limit(limit)
    ).all()

    slots = bookable_slots_by_webinar(db, [webinar.id for webinar in webinars], now)
    return [CatalogEntry(webinar, slots.get(webinar.id, [])) for webinar in webinars], total


def get_catalog_entry(db: Session, webinar_id: UUID) -> CatalogEntry:
    webinar = db.get(Webinar, webinar_id)
    if webinar is None or webinar.status != RecordStatus.ACTIVE:
        raise WebinarUnavailable
    return CatalogEntry(webinar, bookable_slots_by_webinar(db, [webinar.id]).get(webinar.id, []))


def bookable_slots_by_webinar(
    db: Session, webinar_ids: list[UUID], now: datetime | None = None
) -> dict[UUID, list[Slot]]:
    if not webinar_ids:
        return {}
    now = now or datetime.now(UTC)
    slots = db.scalars(
        select(Slot).where(Slot.webinar_id.in_(webinar_ids), *_bookable(now)).order_by(Slot.start_at, Slot.id)
    ).all()
    grouped: dict[UUID, list[Slot]] = defaultdict(list)
    for slot in slots:
        grouped[slot.webinar_id].append(slot)
    return grouped


def _bookable(now: datetime) -> tuple:
    return Slot.status == SlotStatus.ACTIVE, Slot.start_at > now


def _filtered(
    query: Select,
    *,
    status: RecordStatus | None,
    department_id: UUID | None,
    q: str | None,
    active_department_only: bool = False,
) -> Select:
    if status is not None:
        query = query.where(Webinar.status == status)
    if department_id is not None:
        condition = Department.id == department_id
        if active_department_only:
            condition = condition & (Department.status == RecordStatus.ACTIVE)
        query = query.where(Webinar.departments.any(condition))
    if q:
        query = query.where(Webinar.title.ilike(contains_pattern(q), escape="\\"))
    return query
