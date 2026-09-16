"""Idempotent seed data: default departments and the reminder schedule.

Run: python -m app.scripts.seed
"""

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import SessionLocal
from app.models import Department, ReminderRule

DEPARTMENTS = [
    ("Computer Science and Engineering", "CSE — programming, systems and software engineering."),
    ("Artificial Intelligence / Machine Learning", "AI/ML — machine learning, deep learning and applied AI."),
    ("Data Science", "Data analysis, statistics, SQL and visualisation."),
    ("Information Technology", "IT — software development, databases, networking and enterprise systems."),
    ("Electronics and Communication Engineering", "ECE — embedded systems, IoT, VLSI and communication systems."),
    ("Electrical and Electronics Engineering", "EEE — power systems, control systems and electronics."),
    ("Mechanical Engineering", "Mechanical — design, CAD/CAM, automation and robotics."),
    ("Civil Engineering", "Civil — structural design, construction technology and CAD."),
    ("Cyber Security", "Network security, ethical hacking and digital forensics."),
    ("Cloud Computing and DevOps", "Cloud platforms, containers, CI/CD and infrastructure automation."),
    ("Computer Applications (MCA / BCA)", "Programming, web and application development for MCA and BCA learners."),
    ("Business Analytics and Management", "MBA/BBA — business analytics, digital marketing and data-driven decisions."),
]

# (offset_days, local send time) — decision D8. Day-of time is further clamped to start−2h at send time.
REMINDER_RULES = [(3, time(9, 0)), (2, time(9, 0)), (1, time(9, 0)), (0, time(8, 0))]


def seed(db: Session) -> None:
    existing_departments = set(db.scalars(select(Department.name)))
    for name, description in DEPARTMENTS:
        if name not in existing_departments:
            db.add(Department(name=name, description=description))

    existing_offsets = set(db.scalars(select(ReminderRule.offset_days)))
    for offset_days, send_time in REMINDER_RULES:
        if offset_days not in existing_offsets:
            db.add(ReminderRule(offset_days=offset_days, send_time_local=send_time))

    db.flush()


def main() -> None:
    with SessionLocal() as db:
        seed(db)
        db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    main()
