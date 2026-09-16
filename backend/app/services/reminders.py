"""Automated webinar reminders (PRD FR-12, 8.17–8.18; decision D8).

Each active `ReminderRule` means "N days before the session, at a local (IST) time". The
scheduler calls `enqueue_due_reminders` every few minutes; it queues at most one reminder per
booking per run — the most recent rule that has come due — so a booking made late, or a
scheduler that was down, never gets a stale "in 3 days" message. Reminders that came due
before the booking was confirmed are skipped. The unique index on reminder notifications makes
repeated runs harmless (BR-09).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Booking, BookingStatus, ReminderRule, Slot, SlotStatus
from app.services.errors import Conflict, NotFound, ServiceError
from app.services.notifications import notify_reminder

SAME_DAY_LEAD = timedelta(hours=2)


class ReminderRuleNotFound(NotFound):
    message = "Reminder rule not found."


class ReminderOffsetTaken(Conflict):
    message = "A reminder rule for that many days before the session already exists."


class InvalidReminderRule(ServiceError):
    message = "A reminder rule must send at least one of email or SMS."


# --- scheduling ----------------------------------------------------------------


def reminder_due_at(rule: ReminderRule, start_at: datetime) -> datetime:
    """When `rule` should fire for a session starting at `start_at` (returned in UTC).

    Same-day reminders go out at the rule's time or two hours before the start, whichever is earlier.
    """
    local_zone = ZoneInfo(get_settings().timezone)
    session_day = start_at.astimezone(local_zone).date()
    due = datetime.combine(session_day - timedelta(days=rule.offset_days), rule.send_time_local, tzinfo=local_zone)
    if rule.offset_days == 0:
        due = min(due, start_at - SAME_DAY_LEAD)
    return due.astimezone(UTC)


def enqueue_due_reminders(db: Session, now: datetime | None = None) -> int:
    """Queue due reminders for confirmed upcoming bookings. Returns the number of notifications queued."""
    now = now or datetime.now(UTC)
    rules = list(
        db.scalars(
            select(ReminderRule).where(
                ReminderRule.active.is_(True), or_(ReminderRule.send_email.is_(True), ReminderRule.send_sms.is_(True))
            )
        )
    )
    if not rules:
        return 0

    horizon = now + timedelta(days=max(rule.offset_days for rule in rules) + 1)
    bookings = db.scalars(
        select(Booking)
        .join(Booking.slot)
        .where(
            Booking.status == BookingStatus.CONFIRMED,
            Slot.status == SlotStatus.ACTIVE,
            Slot.start_at > now,
            Slot.start_at <= horizon,
        )
        .options(selectinload(Booking.user), selectinload(Booking.webinar), selectinload(Booking.slot))
    ).all()

    queued = 0
    for booking in bookings:
        rule = _latest_due_rule(rules, booking, now)
        if rule is not None:
            queued += notify_reminder(
                db, booking, offset_days=rule.offset_days, email=rule.send_email, sms=rule.send_sms
            )
    return queued


def _latest_due_rule(rules: list[ReminderRule], booking: Booking, now: datetime) -> ReminderRule | None:
    due = [(reminder_due_at(rule, booking.slot.start_at), rule) for rule in rules]
    due = [(at, rule) for at, rule in due if at <= now]
    if not due:
        return None
    due_at, rule = max(due, key=lambda item: item[0])
    confirmed_at = booking.confirmed_at or booking.created_at
    return rule if due_at >= confirmed_at else None


# --- rule management (admin) ---------------------------------------------------


def list_rules(db: Session) -> list[ReminderRule]:
    return list(db.scalars(select(ReminderRule).order_by(ReminderRule.offset_days.desc())))


def get_rule(db: Session, rule_id: UUID) -> ReminderRule:
    rule = db.get(ReminderRule, rule_id)
    if rule is None:
        raise ReminderRuleNotFound
    return rule


def create_rule(db: Session, fields: dict[str, Any]) -> ReminderRule:
    rule = ReminderRule(**fields)
    _validate_and_flush(db, rule)
    return rule


def update_rule(db: Session, rule_id: UUID, changes: dict[str, Any]) -> ReminderRule:
    rule = get_rule(db, rule_id)
    for field, value in changes.items():
        setattr(rule, field, value)
    _validate_and_flush(db, rule)
    return rule


def delete_rule(db: Session, rule_id: UUID) -> None:
    db.delete(get_rule(db, rule_id))
    db.flush()


def _validate_and_flush(db: Session, rule: ReminderRule) -> None:
    if not (rule.send_email or rule.send_sms):
        raise InvalidReminderRule
    try:
        with db.begin_nested():
            db.add(rule)
            db.flush()
    except IntegrityError as exc:  # unique offset_days
        raise ReminderOffsetTaken from exc
