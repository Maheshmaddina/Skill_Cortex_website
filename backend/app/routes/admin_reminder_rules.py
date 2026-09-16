from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import DbSession, require_admin
from app.models import ReminderRule
from app.schemas.reminder import ReminderRuleCreate, ReminderRuleOut, ReminderRuleUpdate
from app.services import reminders as reminder_service

router = APIRouter(
    prefix="/admin/reminder-rules", tags=["admin: reminders"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=list[ReminderRuleOut])
def list_rules(db: DbSession) -> list[ReminderRule]:
    """The reminder schedule, furthest-out first. Times are in the platform timezone (IST)."""
    return reminder_service.list_rules(db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReminderRuleOut)
def create_rule(payload: ReminderRuleCreate, db: DbSession) -> ReminderRule:
    rule = reminder_service.create_rule(db, payload.model_dump())
    db.commit()
    return rule


@router.put("/{rule_id}", response_model=ReminderRuleOut)
def update_rule(rule_id: UUID, payload: ReminderRuleUpdate, db: DbSession) -> ReminderRule:
    rule = reminder_service.update_rule(db, rule_id, payload.model_dump(exclude_unset=True))
    db.commit()
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: UUID, db: DbSession) -> None:
    """Remove a rule. Reminders already sent are unaffected; set `active: false` to pause instead."""
    reminder_service.delete_rule(db, rule_id)
    db.commit()
