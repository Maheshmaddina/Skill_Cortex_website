from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import AdminUser, DbSession, PageParams, require_admin
from app.models import UserRole
from app.schemas.admin import AdminUserOut, AdminUserUpdate
from app.schemas.common import Page
from app.services import admin_users as user_service

router = APIRouter(prefix="/admin/users", tags=["admin: users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=Page[AdminUserOut])
def list_users(
    db: DbSession,
    pagination: PageParams,
    q: Annotated[str | None, Query(max_length=100, description="Name, email or phone")] = None,
    department_id: UUID | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[AdminUserOut]:
    """Users, newest first, with booking and payment totals. For a user's bookings and payments use
    `/admin/bookings?user_id=` and `/admin/payments?user_id=`."""
    summaries, total = user_service.list_users(
        db,
        q=q,
        department_id=department_id,
        role=role,
        is_active=is_active,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[AdminUserOut](
        items=[AdminUserOut.from_summary(s) for s in summaries],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(user_id: UUID, db: DbSession) -> AdminUserOut:
    return AdminUserOut.from_summary(user_service.get_user_summary(db, user_id))


@router.put("/{user_id}", response_model=AdminUserOut)
def update_user(user_id: UUID, payload: AdminUserUpdate, admin: AdminUser, db: DbSession) -> AdminUserOut:
    """Activate or deactivate an account. Deactivation signs the user out everywhere; bookings are kept."""
    summary = user_service.set_user_active(db, admin, user_id, payload.is_active)
    db.commit()
    return AdminUserOut.from_summary(summary)
