from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.services.notification_messages import (
    admin_payment,
    booking_confirmed,
    format_amount,
    format_date,
    format_inr,
    format_time,
)
from tests.factories import make_slot, make_user, make_webinar
from tests.test_payments import paid_booking


def test_rupees_use_indian_digit_grouping() -> None:
    assert format_inr(99_900) == "₹999"
    assert format_inr(14_990_050) == "₹1,49,900.50"
    assert format_inr(1_00_00_000_00) == "₹1,00,00,000"  # one crore
    assert format_inr(5) == "₹0.05"
    assert format_amount(0) == "Free"


def test_times_are_shown_in_ist() -> None:
    start = datetime(2026, 9, 20, 4, 30, tzinfo=UTC)

    assert format_date(start) == "Sun, 20 Sep 2026"
    assert format_time(start) == "10:00 AM"


def _booking_on_20_september(db: Session):
    slot = make_slot(db, make_webinar(db, title="Python Programming"))
    slot.start_at = datetime(2026, 9, 20, 4, 30, tzinfo=UTC)
    slot.end_at = slot.start_at + timedelta(hours=1)
    db.flush()
    return paid_booking(db, make_user(db, email="learner@example.com"), slot)


def test_booking_confirmation_has_everything_the_prd_lists(db: Session) -> None:
    booking, payment = _booking_on_20_september(db)

    message = booking_confirmed(booking, payment)

    for expected in (
        "Hi Test User",
        "Webinar: Python Programming",
        "Date: Sun, 20 Sep 2026",
        "Time: 10:00 AM – 11:00 AM IST",
        "Amount paid: ₹999",
        f"Booking ID: {booking.reference}",
        f"Payment reference: {payment.razorpay_payment_id}",
    ):
        assert expected in message.email_text
    assert message.sms_text.startswith(f"Skill Cortex: Booking {booking.reference} confirmed")
    assert len(message.sms_text) < 200
    assert message.variables["time"] == "10:00 AM"


def test_admin_payment_message_includes_learner_contact_and_status(db: Session) -> None:
    booking, payment = _booking_on_20_september(db)

    message = admin_payment(booking, payment)

    for expected in ("Email: learner@example.com", "Phone: 9876543210", "Status: PAID", "Amount: ₹999"):
        assert expected in message.email_text
    assert message.subject.startswith("New payment received")
