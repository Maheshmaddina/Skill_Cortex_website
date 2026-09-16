"""Background jobs. Each opens its own session and commits; all are safe to run concurrently."""

import logging

from app.database import SessionLocal
from app.services.bookings import complete_finished_bookings, expire_stale_bookings
from app.services.learner_sessions import withdraw_unused_learner_sessions
from app.services.notifications import get_notification_dispatcher
from app.services.rate_limit import purge_expired
from app.services.reminders import enqueue_due_reminders

logger = logging.getLogger(__name__)


def expire_stale_bookings_job() -> None:
    with SessionLocal() as db:
        count = expire_stale_bookings(db)
        withdrawn = withdraw_unused_learner_sessions(db)
        db.commit()
    if count:
        logger.info("Released %d expired seat hold(s).", count)
    if withdrawn:
        logger.info("Withdrew %d unused learner-set session(s).", withdrawn)


def complete_finished_bookings_job() -> None:
    with SessionLocal() as db:
        count = complete_finished_bookings(db)
        db.commit()
    if count:
        logger.info("Marked %d booking(s) as completed.", count)


def dispatch_notifications_job() -> None:
    """Safety net for the post-request dispatch: sends anything left PENDING and retries failures."""
    get_notification_dispatcher().dispatch_pending()


def purge_rate_limits_job() -> None:
    count = purge_expired()
    if count:
        logger.info("Purged %d expired rate-limit counter(s).", count)


def send_reminders_job() -> None:
    with SessionLocal() as db:
        count = enqueue_due_reminders(db)
        db.commit()
    if count:
        logger.info("Queued %d reminder notification(s).", count)
        get_notification_dispatcher().dispatch_pending()
