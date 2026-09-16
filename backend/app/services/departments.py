from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Department, RecordStatus
from app.services.errors import Conflict, NotFound, ServiceError


class DepartmentNotAvailable(ServiceError):
    message = "Selected department is not available."


class DepartmentNotFound(NotFound):
    message = "Department not found."


class DepartmentNameTaken(Conflict):
    message = "A department with this name already exists."


def list_active_departments(db: Session) -> list[Department]:
    query = select(Department).where(Department.status == RecordStatus.ACTIVE).order_by(Department.name)
    return list(db.scalars(query))


def list_all_departments(db: Session) -> list[Department]:
    return list(db.scalars(select(Department).order_by(Department.name)))


def get_active_department(db: Session, department_id: UUID) -> Department:
    department = db.get(Department, department_id)
    if department is None or department.status != RecordStatus.ACTIVE:
        raise DepartmentNotAvailable
    return department


def get_department(db: Session, department_id: UUID) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise DepartmentNotFound
    return department


def create_department(db: Session, *, name: str, description: str | None) -> Department:
    _ensure_name_available(db, name)
    department = Department(name=name, description=description)
    _flush_unique_name(db, department)
    return department


def update_department(db: Session, department_id: UUID, changes: dict[str, Any]) -> Department:
    """Apply a partial update. Deactivation is `{"status": INACTIVE}` (soft delete)."""
    department = get_department(db, department_id)
    if "name" in changes:
        _ensure_name_available(db, changes["name"], exclude_id=department.id)
    for field, value in changes.items():
        setattr(department, field, value)
    _flush_unique_name(db, department)
    return department


def _ensure_name_available(db: Session, name: str, exclude_id: UUID | None = None) -> None:
    query = select(Department.id).where(func.lower(Department.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Department.id != exclude_id)
    if db.scalar(query) is not None:
        raise DepartmentNameTaken


def _flush_unique_name(db: Session, department: Department) -> None:
    try:
        with db.begin_nested():
            db.add(department)
            db.flush()
    except IntegrityError as exc:  # lost a race with a concurrent create/rename
        raise DepartmentNameTaken from exc
