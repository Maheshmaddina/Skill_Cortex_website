from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import RecordStatus
from app.schemas.department import DepartmentOut
from app.schemas.slot import SlotOut

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=10_000)]
Instructor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
PricePaise = Annotated[int, Field(ge=0, le=10_000_000)]  # up to ₹1,00,000
DurationMinutes = Annotated[int, Field(ge=1, le=24 * 60)]
DepartmentIds = Annotated[list[UUID], Field(min_length=1)]


class WebinarCreate(BaseModel):
    title: Title
    description: Description
    instructor: Instructor | None = None
    price_paise: PricePaise
    duration_minutes: DurationMinutes
    department_ids: DepartmentIds
    status: RecordStatus = RecordStatus.ACTIVE


class WebinarUpdate(BaseModel):
    # Non-nullable fields default to None so they can be omitted, but an explicit null is rejected.
    title: Title = None
    description: Description = None
    instructor: Instructor | None = None
    price_paise: PricePaise = None
    duration_minutes: DurationMinutes = None
    department_ids: DepartmentIds = None
    status: RecordStatus = None


class WebinarAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str
    instructor: str | None
    price_paise: int
    duration_minutes: int
    status: RecordStatus
    departments: list[DepartmentOut]
    created_at: datetime
    updated_at: datetime


class WebinarCard(BaseModel):
    """Catalog listing card (PRD 8.6)."""

    id: UUID
    title: str
    short_description: str
    price_paise: int
    duration_minutes: int
    departments: list[DepartmentOut]
    next_slot: SlotOut | None
    available_seats: int
    # With ?preferred_date (and optional preferred_time): an open session on that IST date (at that start time).
    matching_slot: SlotOut | None = None


class WebinarDetail(BaseModel):
    """Webinar details page (PRD 8.7)."""

    id: UUID
    title: str
    description: str
    instructor: str | None
    price_paise: int
    duration_minutes: int
    departments: list[DepartmentOut]
    slots: list[SlotOut]
