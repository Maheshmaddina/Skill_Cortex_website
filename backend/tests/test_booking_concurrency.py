"""Real concurrent transactions (not the rolled-back test session) racing for the last seats."""

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.models import Booking, Slot, User, Webinar
from app.services.bookings import SlotFull, create_booking
from tests.factories import make_slot, make_user, make_webinar


def test_concurrent_bookings_never_oversell_a_slot(engine: Engine) -> None:
    capacity, attempts = 3, 12

    with Session(engine) as setup:
        webinar = make_webinar(setup, title="Concurrency test")
        slot = make_slot(setup, webinar, capacity=capacity)
        users = [make_user(setup) for _ in range(attempts)]
        setup.commit()
        webinar_id, slot_id, user_ids = webinar.id, slot.id, [user.id for user in users]

    start_together = threading.Barrier(attempts)

    def attempt(user_id) -> str:
        with Session(engine) as session:
            user = session.get(User, user_id)
            start_together.wait()
            try:
                create_booking(session, user, slot_id)
                session.commit()
                return "booked"
            except SlotFull:
                session.rollback()
                return "full"

    try:
        with ThreadPoolExecutor(max_workers=attempts) as pool:
            outcomes = list(pool.map(attempt, user_ids))

        assert outcomes.count("booked") == capacity
        assert outcomes.count("full") == attempts - capacity
        with Session(engine) as check:
            assert check.get(Slot, slot_id).available_seats == 0
            assert check.scalar(select(func.count()).where(Booking.slot_id == slot_id)) == capacity
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(Booking).where(Booking.slot_id == slot_id))
            cleanup.execute(delete(Slot).where(Slot.id == slot_id))
            cleanup.execute(delete(Webinar).where(Webinar.id == webinar_id))
            cleanup.execute(delete(User).where(User.id.in_(user_ids)))
            cleanup.commit()
