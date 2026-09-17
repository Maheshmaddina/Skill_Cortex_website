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


def test_paid_confirmation_carries_the_payment_receipt(db: Session) -> None:
    booking, payment = _booking_on_20_september(db)

    message = booking_confirmed(booking, payment)

    for expected in (
        "PAYMENT RECEIPT",
        f"Receipt no.: {booking.reference}",
        "Billed to: Test User · learner@example.com · 9876543210",
        "Amount paid (incl. all taxes): ₹999",
        "Payment method: Card / Netbanking / Wallet (Razorpay)",
        f"/bookings/{booking.id}/receipt",
    ):
        assert expected in message.email_text
    assert message.email_html is not None
    assert "Payment receipt" in message.email_html and "View receipt" in message.email_html
    assert booking.reference in message.email_html


def test_upi_receipt_shows_the_transaction_id(db: Session) -> None:
    from app.models import PaymentMethod

    booking, payment = _booking_on_20_september(db)
    payment.method, payment.razorpay_order_id, payment.razorpay_payment_id = PaymentMethod.UPI, None, None
    payment.upi_reference = "412345678901"

    for message in (booking_confirmed(booking, payment), admin_payment(booking, payment)):
        assert "Payment method: UPI" in message.email_text
        assert "UPI transaction ID 412345678901" in message.email_text
        assert "UPI transaction ID 412345678901" in message.email_html


def test_admin_payment_email_has_the_receipt_and_escapes_learner_input(db: Session) -> None:
    booking, payment = _booking_on_20_september(db)
    booking.user.name = "<b>Asha</b>"

    message = admin_payment(booking, payment)

    assert "PAYMENT RECEIPT" in message.email_text
    assert "&lt;b&gt;Asha&lt;/b&gt;" in message.email_html
    assert "<b>Asha</b>" not in message.email_html


def test_free_confirmation_has_no_receipt(db: Session) -> None:
    booking, _ = _booking_on_20_september(db)
    message = booking_confirmed(booking, None)
    assert "PAYMENT RECEIPT" not in message.email_text
    assert message.email_html is None
