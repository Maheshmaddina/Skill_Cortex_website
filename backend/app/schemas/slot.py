from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, computed_field

from app.models import SlotStatus

Capacity = Annotated[int, Field(ge=1, le=10_000)]
# Clients may send any offset (e.g. +05:30); normalise to UTC so every response uses the same form.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    webinar_id: UUID
    start_at: datetime
    end_at: datetime
    capacity: int
    available_seats: int

    @computed_field
    @property
    def is_full(self) -> bool:
        return self.available_seats == 0


class SlotWebinar(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str


class SlotSetBy(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone: str


class SlotAdminOut(SlotOut):
    status: SlotStatus
    created_at: datetime
    updated_at: datetime
    webinar: SlotWebinar
    set_by: SlotSetBy | None  # the learner who chose this date and time, if it wasn't admin-published
    learner_note: str | None

    @computed_field
    @property
    def booked_seats(self) -> int:
        """Seats taken by confirmed bookings and unexpired payment holds."""
        return self.capacity - self.available_seats


class SlotCreate(BaseModel):
    webinar_id: UUID
    start_at: UtcDatetime
    end_at: UtcDatetime
    capacity: Capacity


class SlotUpdate(BaseModel):
    # Non-nullable fields default to None so they can be omitted, but an explicit null is rejected.
    start_at: UtcDatetime = None
    end_at: UtcDatetime = None
    capacity: Capacity = None
    status: SlotStatus = None
