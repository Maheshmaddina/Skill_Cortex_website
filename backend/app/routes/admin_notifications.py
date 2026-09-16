from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.dependencies import DbSession, Notifier, PageParams, require_admin
from app.models import Notification, NotificationChannel, NotificationStatus, NotificationType
from app.schemas.common import Page
from app.schemas.notification import NotificationAdminOut
from app.services import notifications as notification_service

router = APIRouter(
    prefix="/admin/notifications", tags=["admin: notifications"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=Page[NotificationAdminOut])
def list_notifications(
    db: DbSession,
    pagination: PageParams,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    type_filter: Annotated[NotificationType | None, Query(alias="type")] = None,
    channel: NotificationChannel | None = None,
    booking_id: UUID | None = None,
    user_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Recipient address or subject")] = None,
) -> Page[NotificationAdminOut]:
    rows, total = notification_service.list_notifications(
        db,
        user_id=user_id,
        status=status_filter,
        type_=type_filter,
        channel=channel,
        booking_id=booking_id,
        q=q,
        offset=pagination.offset,
        limit=pagination.page_size,
    )
    return Page[NotificationAdminOut](
        items=[NotificationAdminOut.model_validate(n) for n in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{notification_id}", response_model=NotificationAdminOut)
def get_notification(notification_id: UUID, db: DbSession) -> Notification:
    return notification_service.get_notification(db, notification_id)


@router.post("/{notification_id}/retry", response_model=NotificationAdminOut)
def retry_notification(
    notification_id: UUID, db: DbSession, background_tasks: BackgroundTasks, notifier: Notifier
) -> Notification:
    """Queue a failed (or stuck) notification for another delivery attempt."""
    notification = notification_service.retry_notification(db, notification_id)
    db.commit()
    background_tasks.add_task(notifier.dispatch_pending)
    return notification
