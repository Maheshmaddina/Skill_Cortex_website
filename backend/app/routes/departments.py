from uuid import UUID

from fastapi import APIRouter

from app.dependencies import DbSession
from app.models import Department
from app.schemas.department import DepartmentOut
from app.services.departments import (
    DepartmentNotAvailable,
    DepartmentNotFound,
    get_active_department,
    list_active_departments,
)

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: DbSession) -> list[Department]:
    return list_active_departments(db)


@router.get("/{department_id}", response_model=DepartmentOut)
def get_department(department_id: UUID, db: DbSession) -> Department:
    try:
        return get_active_department(db, department_id)
    except DepartmentNotAvailable:
        raise DepartmentNotFound from None
