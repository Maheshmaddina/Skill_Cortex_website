from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession, PageParams
from app.schemas.common import Page
from app.schemas.notification import NotificationOut
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut])
def list_my_notifications(user: CurrentUser, db: DbSession, pagination: PageParams) -> Page[NotificationOut]:
    """Messages sent (or queued) to the logged-in learner, newest first."""
    rows, total = notification_service.list_notifications(
        db, user_id=user.id, offset=pagination.offset, limit=pagination.page_size
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(n) for n in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
