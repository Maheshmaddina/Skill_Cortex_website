from fastapi import APIRouter, status

from app.dependencies import CurrentUser, DbSession, PageParams
from app.schemas.common import Page
from app.schemas.notification import NotificationOut, UnreadCount
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationOut])
def list_my_notifications(user: CurrentUser, db: DbSession, pagination: PageParams) -> Page[NotificationOut]:
    """Messages sent (or queued) to the logged-in learner, newest first — one entry per message."""
    rows, total = notification_service.list_inbox(db, user, offset=pagination.offset, limit=pagination.page_size)
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(n) for n in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: CurrentUser, db: DbSession) -> UnreadCount:
    """How many messages arrived since the learner last opened their notifications (for the menu badge)."""
    return UnreadCount(count=notification_service.unread_count(db, user))


@router.post("/mark-seen", status_code=status.HTTP_204_NO_CONTENT)
def mark_seen(user: CurrentUser, db: DbSession) -> None:
    notification_service.mark_inbox_seen(db, user)
    db.commit()
