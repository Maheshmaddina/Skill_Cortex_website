from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import DbSession, PageParams, require_admin
from app.models import RecordStatus, Webinar
from app.schemas.common import Page
from app.schemas.webinar import WebinarAdminOut, WebinarCreate, WebinarUpdate
from app.services import webinars as webinar_service

router = APIRouter(prefix="/admin/webinars", tags=["admin: webinars"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[WebinarAdminOut])
def list_webinars(
    db: DbSession,
    pagination: PageParams,
    status_filter: Annotated[RecordStatus | None, Query(alias="status")] = None,
    department_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[WebinarAdminOut]:
    webinars, total = webinar_service.list_webinars(
        db,
        status=status_filter,
        department_id=department_id,
        q=q,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[WebinarAdminOut](
        items=[WebinarAdminOut.model_validate(w) for w in webinars],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WebinarAdminOut)
def create_webinar(payload: WebinarCreate, db: DbSession) -> Webinar:
    webinar = webinar_service.create_webinar(db, **payload.model_dump())
    db.commit()
    return webinar


@router.get("/{webinar_id}", response_model=WebinarAdminOut)
def get_webinar(webinar_id: UUID, db: DbSession) -> Webinar:
    return webinar_service.get_webinar(db, webinar_id)


@router.put("/{webinar_id}", response_model=WebinarAdminOut)
def update_webinar(webinar_id: UUID, payload: WebinarUpdate, db: DbSession) -> Webinar:
    webinar = webinar_service.update_webinar(db, webinar_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return webinar


@router.delete("/{webinar_id}", response_model=WebinarAdminOut)
def deactivate_webinar(webinar_id: UUID, db: DbSession) -> Webinar:
    """Soft delete: hidden from the catalog and no longer bookable; existing bookings are kept."""
    webinar = webinar_service.update_webinar(db, webinar_id, {"status": RecordStatus.INACTIVE})
    db.commit()
    return webinar
