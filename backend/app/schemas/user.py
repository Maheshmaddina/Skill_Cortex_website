import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from app.models import UserRole
from app.schemas.department import DepartmentOut

INDIAN_MOBILE = re.compile(r"[6-9]\d{9}")


def normalize_phone(value: str) -> str:
    """Accept '98765 43210', '+91-9876543210' etc.; store the 10 digits."""
    digits = re.sub(r"[\s-]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    if not INDIAN_MOBILE.fullmatch(digits):
        raise ValueError("Enter a valid 10-digit Indian mobile number.")
    return digits


def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(value.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one letter and one digit.")
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Phone = Annotated[str, AfterValidator(normalize_phone)]
Password = Annotated[str, AfterValidator(validate_password_strength)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    phone: str
    role: UserRole
    department: DepartmentOut | None
    created_at: datetime


class UserUpdate(BaseModel):
    name: Name | None = None
    phone: Phone | None = None
    department_id: UUID | None = None
