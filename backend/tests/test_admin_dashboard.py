from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import (
    BookingStatus,
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PaymentStatus,
    RecipientType,
    RecordStatus,
    SlotStatus,
)
from tests.factories import make_booking, make_payment, make_slot, make_user, make_webinar


def test_dashboard_stats(client: TestClient, db: Session, admin_headers: dict, learner_headers: dict) -> None:
    now = datetime.now(UTC)
    # learner_headers already created one learner; the admin isn't counted as a learner.
    learners = [make_user(db), make_user(db)]
    veteran = make_user(db)
    veteran.created_at = now - timedelta(days=40)

    python = make_webinar(db, title="Python")
    sql = make_webinar(db, title="SQL")
    make_webinar(db, title="Retired", status=RecordStatus.INACTIVE)

    soon = make_slot(db, python, capacity=10, available_seats=7, starts_in=timedelta(days=1))
    later = make_slot(db, sql, capacity=20, starts_in=timedelta(days=5))
    past = make_slot(db, python, starts_in=timedelta(days=-3))
    make_slot(db, sql, starts_in=timedelta(days=2), status=SlotStatus.INACTIVE)

    confirmed = make_booking(db, learners[0], soon, BookingStatus.CONFIRMED)
    old_confirmed = make_booking(db, learners[1], past, BookingStatus.COMPLETED)
    pending = make_booking(db, veteran, soon)
    cancelled = make_booking(db, learners[1], later, BookingStatus.CANCELLED)
    failed_booking = make_booking(db, veteran, later, BookingStatus.EXPIRED)

    recent_paid = make_payment(db, confirmed, PaymentStatus.PAID)
    recent_paid.paid_at = now - timedelta(days=1)
    old_paid = make_payment(db, old_confirmed, PaymentStatus.PAID)
    old_paid.amount_paise, old_paid.paid_at = 149_900, now - timedelta(days=45)
    make_payment(db, pending)
    make_payment(db, cancelled, PaymentStatus.REFUNDED)
    make_payment(db, failed_booking, PaymentStatus.FAILED)

    statuses = (NotificationStatus.FAILED, NotificationStatus.PENDING, NotificationStatus.PENDING, NotificationStatus.SENT)
    for index, status in enumerate(statuses):
        db.add(
            Notification(
                booking_id=confirmed.id,
                recipient_type=RecipientType.ADMIN,
                recipient_address=f"ops-{index}@example.com",  # one message per recipient (unique index)
                type=NotificationType.ADMIN_PAYMENT,
                channel=NotificationChannel.EMAIL,
                message="x",
                status=status,
            )
        )
    db.flush()

    response = client.get("/admin/dashboard/stats", headers=admin_headers)

    assert response.status_code == 200
    stats = response.json()
    assert stats["users"] == {"learners": 4, "new_learners_last_30_days": 3, "admins": 1}
    assert stats["webinars"] == {"total": 3, "active": 2}
    assert stats["upcoming_sessions_count"] == 2
    assert stats["bookings"] == {
        "total": 5,
        "pending": 1,
        "confirmed": 1,
        "expired": 1,
        "failed": 0,
        "cancelled": 1,
        "completed": 1,
    }
    assert stats["payments"] == {"successful": 2, "pending": 1, "failed": 1, "refunded": 1, "upi_awaiting_verification": 0}
    assert stats["revenue"] == {"total_paise": 99_900 + 149_900, "last_30_days_paise": 99_900}
    assert stats["notifications"] == {"pending": 2, "failed": 1}
    assert [
        (s["webinar_title"], s["capacity"], s["booked_seats"], s["available_seats"]) for s in stats["upcoming_sessions"]
    ] == [("Python", 10, 3, 7), ("SQL", 20, 0, 20)]


def test_dashboard_on_an_empty_platform(client: TestClient, admin_headers: dict) -> None:
    stats = client.get("/admin/dashboard/stats", headers=admin_headers).json()

    assert stats["revenue"] == {"total_paise": 0, "last_30_days_paise": 0}
    assert stats["bookings"]["total"] == 0
    assert stats["upcoming_sessions"] == []


def test_dashboard_requires_admin(client: TestClient, learner_headers: dict) -> None:
    assert client.get("/admin/dashboard/stats").status_code == 401
    assert client.get("/admin/dashboard/stats", headers=learner_headers).status_code == 403
