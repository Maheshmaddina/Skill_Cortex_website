from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, RecordStatus, Slot, SlotStatus, User, Webinar
from app.services.learner_sessions import LEARNER_SESSION_CAPACITY, withdraw_unused_learner_sessions
from tests.factories import auth_header, make_user, make_webinar

IST = ZoneInfo("Asia/Kolkata")


def in_days(days: int) -> date:
    return datetime.now(IST).date() + timedelta(days=days)


def set_webinar(client: TestClient, user: User, webinar: Webinar, day: date, at: str = "18:30", **extra):
    payload = {"webinar_id": str(webinar.id), "preferred_date": day.isoformat(), "preferred_time": at, **extra}
    return client.post("/bookings/set-webinar", json=payload, headers=auth_header(user))


def slots_of(db: Session, webinar: Webinar) -> list[Slot]:
    return list(db.scalars(select(Slot).where(Slot.webinar_id == webinar.id)))


def test_learner_sets_a_webinar_at_their_own_date_and_time(client: TestClient, db: Session) -> None:
    learner, webinar = make_user(db), make_webinar(db)  # 60-minute course, ₹999

    response = set_webinar(client, learner, webinar, in_days(5), "18:30", note="  After college please ")

    assert response.status_code == 201
    booking = response.json()
    assert booking["status"] == "PENDING"  # pays next, exactly like a normal booking
    assert booking["amount_paise"] == 99_900
    start = datetime.combine(in_days(5), time(18, 30), IST)
    assert datetime.fromisoformat(booking["slot"]["start_at"]) == start
    assert datetime.fromisoformat(booking["slot"]["end_at"]) == start + timedelta(minutes=60)

    [slot] = slots_of(db, webinar)
    assert slot.set_by_user_id == learner.id
    assert slot.learner_note == "After college please"
    assert (slot.capacity, slot.available_seats) == (LEARNER_SESSION_CAPACITY, LEARNER_SESSION_CAPACITY - 1)

    # Pressing it again doesn't take a second seat.
    again = set_webinar(client, learner, webinar, in_days(5), "18:30")
    assert again.status_code == 200
    assert again.json()["id"] == booking["id"]
    db.refresh(slot)
    assert slot.available_seats == LEARNER_SESSION_CAPACITY - 1


def test_another_learner_choosing_the_same_time_joins_the_same_session(client: TestClient, db: Session) -> None:
    webinar = make_webinar(db)
    first, second = make_user(db), make_user(db)

    second.name = "Meena"
    set_webinar(client, first, webinar, in_days(4), "10:00", note="Basics first")
    response = set_webinar(client, second, webinar, in_days(4), "10:00", note="Please cover Spring Security")

    assert response.status_code == 201
    [slot] = slots_of(db, webinar)
    assert slot.set_by_user_id == first.id
    assert slot.available_seats == LEARNER_SESSION_CAPACITY - 2
    assert slot.learner_note == "Basics first\nMeena: Please cover Spring Security"


def test_setting_a_time_that_an_admin_session_already_covers_books_into_it(client: TestClient, db: Session) -> None:
    webinar = make_webinar(db)
    start = datetime.combine(in_days(3), time(14, 0), IST)
    published = Slot(webinar=webinar, start_at=start, end_at=start + timedelta(hours=1), capacity=5, available_seats=5)
    db.add(published)
    db.flush()

    response = set_webinar(client, make_user(db), webinar, in_days(3), "14:00")

    assert response.json()["slot"]["id"] == str(published.id)
    assert slots_of(db, webinar) == [published]

    published.available_seats = 0
    db.flush()
    full = set_webinar(client, make_user(db), webinar, in_days(3), "14:00")
    assert full.status_code == 409
    assert "full" in full.json()["detail"]


def test_dates_and_times_are_validated(client: TestClient, db: Session) -> None:
    learner, webinar = make_user(db), make_webinar(db)
    cases = [
        (in_days(0), "18:30", "from tomorrow"),
        (in_days(91), "18:30", "within the next 90 days"),
        (in_days(3), "06:30", "between 7:00 AM and 9:00 PM"),
        (in_days(3), "21:30", "between 7:00 AM and 9:00 PM"),
        (in_days(3), "10:15", "hour or half hour"),
    ]
    for day, at, message in cases:
        response = set_webinar(client, learner, webinar, day, at)
        assert response.status_code == 400, (day, at)
        assert message in response.json()["detail"]
    assert slots_of(db, webinar) == []


def test_admins_and_inactive_courses_cannot_set_webinars(client: TestClient, db: Session, admin_headers: dict) -> None:
    webinar = make_webinar(db)
    payload = {"webinar_id": str(webinar.id), "preferred_date": in_days(3).isoformat(), "preferred_time": "10:00"}
    assert client.post("/bookings/set-webinar", json=payload, headers=admin_headers).status_code == 403

    inactive = make_webinar(db, title="Old course", status=RecordStatus.INACTIVE)
    assert set_webinar(client, make_user(db), inactive, in_days(3)).status_code == 404


def test_admin_can_list_learner_set_sessions(client: TestClient, db: Session, admin_headers: dict) -> None:
    learner, webinar = make_user(db, email="asha@example.com"), make_webinar(db)
    set_webinar(client, learner, webinar, in_days(6), "16:00", note="Weekend works")
    start = datetime.now(UTC) + timedelta(days=2)
    db.add(Slot(webinar=webinar, start_at=start, end_at=start + timedelta(hours=1), capacity=5, available_seats=5))
    db.flush()

    learner_set = client.get("/admin/slots", params={"learner_set": "true"}, headers=admin_headers).json()

    assert learner_set["total"] == 1
    [slot] = learner_set["items"]
    assert slot["set_by"]["email"] == "asha@example.com"
    assert slot["learner_note"] == "Weekend works"
    assert slot["webinar"]["title"] == webinar.title
    assert client.get("/admin/slots", params={"learner_set": "false"}, headers=admin_headers).json()["total"] == 1

    stats = client.get("/admin/dashboard/stats", headers=admin_headers).json()
    assert stats["upcoming_learner_set_sessions_count"] == 1
    assert [s["set_by_learner"] for s in stats["upcoming_sessions"]] == [False, True]


def test_unpaid_learner_set_sessions_are_withdrawn_after_an_hour(client: TestClient, db: Session) -> None:
    webinar, learner = make_webinar(db), make_user(db)
    booking_id = set_webinar(client, learner, webinar, in_days(5), "18:30").json()["id"]
    [slot] = slots_of(db, webinar)
    later = datetime.now(UTC) + timedelta(hours=2)

    # Still waiting for payment: kept.
    assert withdraw_unused_learner_sessions(db, later) == 0

    booking = db.get(Booking, booking_id)
    booking.status = BookingStatus.EXPIRED
    booking.updated_at = datetime.now(UTC)
    db.flush()
    assert withdraw_unused_learner_sessions(db, datetime.now(UTC) + timedelta(minutes=30)) == 0  # late payment grace
    assert withdraw_unused_learner_sessions(db, later) == 1
    db.refresh(slot)
    assert slot.status == SlotStatus.INACTIVE


def test_confirmed_learner_set_sessions_are_kept(client: TestClient, db: Session) -> None:
    webinar, learner = make_webinar(db), make_user(db)
    booking_id = set_webinar(client, learner, webinar, in_days(5), "18:30").json()["id"]
    db.get(Booking, booking_id).status = BookingStatus.CONFIRMED
    db.flush()

    assert withdraw_unused_learner_sessions(db, datetime.now(UTC) + timedelta(hours=3)) == 0


def test_catalog_cards_report_a_session_at_the_preferred_date_and_time(client: TestClient, db: Session) -> None:
    webinar = make_webinar(db)
    set_webinar(client, make_user(db), webinar, in_days(3), "10:00")
    set_webinar(client, make_user(db), webinar, in_days(3), "18:30")
    morning, evening = sorted(slots_of(db, webinar), key=lambda slot: slot.start_at)

    def matching(**params) -> str | None:
        card = client.get("/webinars", params=params).json()["items"][0]
        return card["matching_slot"] and card["matching_slot"]["id"]

    assert matching() is None
    assert matching(preferred_date=in_days(3).isoformat()) == str(morning.id)
    assert matching(preferred_date=in_days(3).isoformat(), preferred_time="18:30") == str(evening.id)
    assert matching(preferred_date=in_days(3).isoformat(), preferred_time="14:00") is None
