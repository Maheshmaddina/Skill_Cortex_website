from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import RecordStatus

DepartmentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None


class DepartmentAdminOut(DepartmentOut):
    status: RecordStatus
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    name: DepartmentName
    description: str | None = Field(default=None, max_length=2000)


class DepartmentUpdate(BaseModel):
    # Non-nullable fields default to None so they can be omitted, but an explicit null is rejected.
    name: DepartmentName = None
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus = None
