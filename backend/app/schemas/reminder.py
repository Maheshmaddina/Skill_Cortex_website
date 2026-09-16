from datetime import datetime, time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OffsetDays = Annotated[int, Field(ge=0, le=30, description="Days before the session; 0 = same day")]


class ReminderRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    offset_days: int
    send_time_local: time  # in the platform timezone (IST)
    send_email: bool
    send_sms: bool
    active: bool
    updated_at: datetime


class ReminderRuleCreate(BaseModel):
    offset_days: OffsetDays
    send_time_local: time
    send_email: bool = True
    send_sms: bool = True
    active: bool = True


class ReminderRuleUpdate(BaseModel):
    # Non-nullable fields default to None so they can be omitted, but an explicit null is rejected.
    offset_days: OffsetDays = None
    send_time_local: time = None
    send_email: bool = None
    send_sms: bool = None
    active: bool = None
