"""Idempotent starter catalog: Skill Cortex AI courses with a choice of upcoming sessions.

Courses are matched by title and kept in line (price, duration, description, departments).
Each course gets sessions on several days over the next two weeks, each day at a morning,
afternoon and evening time, so learners can pick the date and time that suits them.
Sessions that already exist at the same start time are left alone, so re-running only tops up.
Run after app.scripts.seed (departments must exist): python -m app.scripts.seed_catalog
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import SessionLocal
from app.models import Department, Slot, Webinar

IST = ZoneInfo("Asia/Kolkata")
PRICE_PAISE = 99_900  # ₹999
DURATION_MINUTES = 120
SLOT_CAPACITY = 60
SLOT_TIMES = (time(10, 0), time(14, 0), time(18, 30))  # IST
SLOT_DAY_OFFSETS = (2, 4, 6, 9, 11, 13)  # days from today; staggered by a day for odd-numbered courses

CSE = "Computer Science and Engineering"
AIML = "Artificial Intelligence / Machine Learning"
DS = "Data Science"
IT = "Information Technology"
ECE = "Electronics and Communication Engineering"
EEE = "Electrical and Electronics Engineering"
MECH = "Mechanical Engineering"
CIVIL = "Civil Engineering"
CYBER = "Cyber Security"
CLOUD = "Cloud Computing and DevOps"
MCA = "Computer Applications (MCA / BCA)"
BA = "Business Analytics and Management"

# (title, description, department names)
COURSES = [
    (
        "Python Full Stack Development",
        "Build complete web apps with Python, Django/FastAPI, REST APIs, React, SQL databases and cloud deployment.",
        [CSE, IT, MCA, AIML, DS],
    ),
    (
        "Java Full Stack Development",
        "Core Java, OOP, Spring Boot, Hibernate/JPA, REST APIs, React and MySQL — end to end, project-based.",
        [CSE, IT, MCA, ECE],
    ),
    (
        "MERN Stack Development",
        "MongoDB, Express, React and Node.js: build, secure and deploy a full JavaScript web application.",
        [CSE, IT, MCA],
    ),
    (
        "Artificial Intelligence and Machine Learning",
        "Supervised and unsupervised learning, model evaluation and real-world ML projects with Python and scikit-learn.",
        [AIML, CSE, DS, IT, ECE],
    ),
    (
        "Data Science with Python",
        "NumPy, pandas, statistics, data cleaning, visualisation and predictive modelling on real datasets.",
        [DS, AIML, CSE, IT, BA, MCA],
    ),
    (
        "Data Scientist Career Program",
        "Job-ready track: Python, SQL, statistics, machine learning, a capstone project and interview preparation.",
        [DS, AIML, CSE, IT, BA],
    ),
    (
        "Data Analytics with Excel, SQL and Power BI",
        "Turn raw data into dashboards and business insights using Excel, SQL queries and Power BI.",
        [DS, BA, IT, MCA, CSE, ECE, EEE, MECH, CIVIL],
    ),
    (
        "Generative AI and Prompt Engineering",
        "LLMs, prompt design, retrieval-augmented generation and building practical GenAI applications.",
        [AIML, CSE, DS, IT, MCA, BA],
    ),
    (
        "Deep Learning and Computer Vision",
        "Neural networks, CNNs, transfer learning and image/video projects with TensorFlow and PyTorch.",
        [AIML, DS, CSE, ECE],
    ),
    (
        "Cloud Computing and DevOps with AWS",
        "AWS core services, Linux, Docker, Kubernetes, CI/CD pipelines and infrastructure as code.",
        [CLOUD, CSE, IT, MCA],
    ),
    (
        "Cyber Security and Ethical Hacking",
        "Networking fundamentals, vulnerability assessment, penetration testing and defensive security practice.",
        [CYBER, CSE, IT, ECE, MCA],
    ),
    (
        "Data Structures and Algorithms for Placements",
        "Arrays to graphs and dynamic programming, with coding-interview problem solving in Java or Python.",
        [CSE, IT, MCA, ECE, AIML, DS],
    ),
    (
        "Embedded Systems and IoT",
        "Microcontrollers, sensors, embedded C and connected IoT projects from prototype to cloud dashboard.",
        [ECE, EEE, MECH],
    ),
    (
        "AutoCAD and 3D Design Fundamentals",
        "2D drafting and 3D modelling for engineering drawings, with hands-on design exercises.",
        [MECH, CIVIL, EEE],
    ),
]


def _slot_starts(index: int, today: date) -> list[datetime]:
    return [
        datetime.combine(today + timedelta(days=offset + index % 2), slot_time, IST)
        for offset in SLOT_DAY_OFFSETS
        for slot_time in SLOT_TIMES
    ]


def seed_catalog(db: Session, today: date | None = None) -> tuple[int, int, int]:
    """Returns (created courses, updated courses, added sessions)."""
    today = today or datetime.now(IST).date()
    departments = {department.name: department for department in db.scalars(select(Department))}
    existing = {webinar.title: webinar for webinar in db.scalars(select(Webinar))}
    created = updated = added_slots = 0

    for index, (title, description, department_names) in enumerate(COURSES):
        missing = [name for name in department_names if name not in departments]
        if missing:
            raise SystemExit(f"Missing departments {missing} — run python -m app.scripts.seed first.")
        course_departments = [departments[name] for name in department_names]

        webinar = existing.get(title)
        if webinar:
            webinar.description = description
            webinar.price_paise = PRICE_PAISE
            webinar.duration_minutes = DURATION_MINUTES
            webinar.departments = course_departments
            updated += 1
        else:
            webinar = Webinar(
                title=title,
                description=description,
                price_paise=PRICE_PAISE,
                duration_minutes=DURATION_MINUTES,
                departments=course_departments,
            )
            db.add(webinar)
            created += 1

        existing_starts = {slot.start_at for slot in webinar.slots}
        for start_at in _slot_starts(index, today):
            if start_at in existing_starts:
                continue
            db.add(
                Slot(
                    webinar=webinar,
                    start_at=start_at,
                    end_at=start_at + timedelta(minutes=DURATION_MINUTES),
                    capacity=SLOT_CAPACITY,
                    available_seats=SLOT_CAPACITY,
                )
            )
            added_slots += 1

    db.flush()
    return created, updated, added_slots


def main() -> None:
    with SessionLocal() as db:
        created, updated, added_slots = seed_catalog(db)
        db.commit()
    print(f"Catalog seeded: {created} courses created, {updated} updated, {added_slots} sessions added.")


if __name__ == "__main__":
    main()
