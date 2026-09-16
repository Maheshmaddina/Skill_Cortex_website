from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import DbSession, require_admin
from app.models import Department, RecordStatus
from app.schemas.department import DepartmentAdminOut, DepartmentCreate, DepartmentUpdate
from app.services import departments as department_service

router = APIRouter(
    prefix="/admin/departments", tags=["admin: departments"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[DepartmentAdminOut])
def list_departments(db: DbSession) -> list[Department]:
    return department_service.list_all_departments(db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DepartmentAdminOut)
def create_department(payload: DepartmentCreate, db: DbSession) -> Department:
    department = department_service.create_department(db, name=payload.name, description=payload.description)
    db.commit()
    return department


@router.get("/{department_id}", response_model=DepartmentAdminOut)
def get_department(department_id: UUID, db: DbSession) -> Department:
    return department_service.get_department(db, department_id)


@router.put("/{department_id}", response_model=DepartmentAdminOut)
def update_department(department_id: UUID, payload: DepartmentUpdate, db: DbSession) -> Department:
    department = department_service.update_department(db, department_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return department


@router.delete("/{department_id}", response_model=DepartmentAdminOut)
def deactivate_department(department_id: UUID, db: DbSession) -> Department:
    """Soft delete: the department is hidden from registration and the catalog."""
    department = department_service.update_department(db, department_id, {"status": RecordStatus.INACTIVE})
    db.commit()
    return department
