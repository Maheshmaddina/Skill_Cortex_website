from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.models import User
from app.schemas.user import UserOut, UserUpdate
from app.services.departments import get_active_department

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser) -> User:
    return user


@router.put("/me", response_model=UserOut)
def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession) -> User:
    if payload.name is not None:
        user.name = payload.name
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.department_id is not None:
        user.department = get_active_department(db, payload.department_id)
    db.commit()
    return user
