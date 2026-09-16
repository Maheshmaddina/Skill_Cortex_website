from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Slot, Webinar
from app.scripts.seed import seed
from app.scripts.seed_catalog import COURSES, IST, PRICE_PAISE, SLOT_DAY_OFFSETS, SLOT_TIMES, seed_catalog

SESSIONS_PER_COURSE = len(SLOT_DAY_OFFSETS) * len(SLOT_TIMES)


def catalog_slots(db: Session) -> list[Slot]:
    titles = [title for title, _, _ in COURSES]
    return db.scalars(select(Slot).join(Webinar).where(Webinar.title.in_(titles))).all()


def test_catalog_seed_is_idempotent_and_priced_at_999(db: Session) -> None:
    seed(db)
    today = date(2026, 9, 16)

    assert seed_catalog(db, today) == (len(COURSES), 0, len(COURSES) * SESSIONS_PER_COURSE)
    assert seed_catalog(db, today) == (0, len(COURSES), 0)

    titles = [title for title, _, _ in COURSES]
    webinars = db.scalars(select(Webinar).where(Webinar.title.in_(titles))).all()
    assert len(webinars) == len(COURSES)
    assert {webinar.price_paise for webinar in webinars} == {PRICE_PAISE} == {99_900}
    assert all(webinar.departments for webinar in webinars)

    slots = catalog_slots(db)
    assert len(slots) == len(COURSES) * SESSIONS_PER_COURSE
    assert min(slot.start_at for slot in slots) > datetime.fromisoformat("2026-09-17T00:00:00+05:30")
    assert all(slot.available_seats == slot.capacity for slot in slots)


def test_each_course_offers_several_dates_and_times(db: Session) -> None:
    seed(db)
    seed_catalog(db, date(2026, 9, 16))

    python = db.scalars(select(Webinar).where(Webinar.title == "Python Full Stack Development")).one()
    ist_starts = [slot.start_at.astimezone(IST) for slot in python.slots]
    assert len(ist_starts) == SESSIONS_PER_COURSE
    assert len({start.date() for start in ist_starts}) == len(SLOT_DAY_OFFSETS)
    assert {start.time() for start in ist_starts} == set(SLOT_TIMES)


def test_rerun_on_a_later_day_only_tops_up_new_sessions(db: Session) -> None:
    seed(db)
    seed_catalog(db, date(2026, 9, 16))
    before = len(catalog_slots(db))

    _, _, added = seed_catalog(db, date(2026, 9, 18))

    assert 0 < added < len(COURSES) * SESSIONS_PER_COURSE
    assert len(catalog_slots(db)) == before + added
