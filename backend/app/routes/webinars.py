"""Public catalog — no login required (PRD §10: guests can browse)."""

from datetime import date, time
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.config import get_settings
from app.dependencies import DbSession, PageParams
from app.models import Slot
from app.schemas.common import Page
from app.schemas.department import DepartmentOut
from app.schemas.slot import SlotOut
from app.schemas.webinar import WebinarCard, WebinarDetail
from app.services import webinars as webinar_service
from app.services.webinars import CatalogEntry
from app.utils.query import summarize

router = APIRouter(prefix="/webinars", tags=["catalog"])


def _matching_slot(entry: CatalogEntry, preferred_date: date | None, preferred_time: time | None) -> Slot | None:
    """First open session on the learner's preferred IST date, at their preferred start time if given."""
    if preferred_date is None:
        return None
    zone = ZoneInfo(get_settings().timezone)
    for slot in entry.bookable_slots:
        local_start = slot.start_at.astimezone(zone)
        if slot.available_seats > 0 and local_start.date() == preferred_date:
            if preferred_time is None or local_start.time() == preferred_time:
                return slot
    return None


def _card(entry: CatalogEntry, preferred_date: date | None = None, preferred_time: time | None = None) -> WebinarCard:
    webinar, next_slot = entry.webinar, entry.next_available_slot
    matching_slot = _matching_slot(entry, preferred_date, preferred_time)
    return WebinarCard(
        id=webinar.id,
        title=webinar.title,
        short_description=summarize(webinar.description),
        price_paise=webinar.price_paise,
        duration_minutes=webinar.duration_minutes,
        departments=[DepartmentOut.model_validate(d) for d in entry.departments],
        next_slot=SlotOut.model_validate(next_slot) if next_slot else None,
        available_seats=entry.available_seats,
        matching_slot=SlotOut.model_validate(matching_slot) if matching_slot else None,
    )


@router.get("", response_model=Page[WebinarCard])
def list_webinars(
    db: DbSession,
    pagination: PageParams,
    department_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    preferred_date: date | None = None,
    preferred_time: time | None = None,
) -> Page[WebinarCard]:
    """`preferred_date`/`preferred_time` (IST) don't filter the list; each card reports a `matching_slot`."""
    entries, total = webinar_service.list_catalog(
        db, department_id=department_id, q=q, offset=pagination.offset, limit=pagination.page_size
    )
    return Page[WebinarCard](
        items=[_card(entry, preferred_date, preferred_time) for entry in entries], total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.get("/{webinar_id}", response_model=WebinarDetail)
def get_webinar(webinar_id: UUID, db: DbSession) -> WebinarDetail:
    entry = webinar_service.get_catalog_entry(db, webinar_id)
    webinar = entry.webinar
    return WebinarDetail(
        id=webinar.id,
        title=webinar.title,
        description=webinar.description,
        instructor=webinar.instructor,
        price_paise=webinar.price_paise,
        duration_minutes=webinar.duration_minutes,
        departments=[DepartmentOut.model_validate(d) for d in entry.departments],
        slots=[SlotOut.model_validate(slot) for slot in entry.bookable_slots],
    )


@router.get("/{webinar_id}/slots", response_model=list[SlotOut])
def list_webinar_slots(webinar_id: UUID, db: DbSession) -> list[Slot]:
    """Upcoming active slots; full ones are included (with `is_full`) so the UI can show them disabled."""
    return webinar_service.get_catalog_entry(db, webinar_id).bookable_slots
