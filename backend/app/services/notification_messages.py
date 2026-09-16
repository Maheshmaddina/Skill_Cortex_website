"""Message content for each notification (PRD 8.14–8.16). Times are shown in IST (decision D10)."""

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models import Booking, Payment, User

SIGN_OFF = "— Team Skill Cortex"


@dataclass(frozen=True)
class RenderedMessage:
    subject: str
    email_text: str
    sms_text: str = ""
    variables: dict[str, str] = field(default_factory=dict)  # named values for SMS templates


def format_inr(paise: int) -> str:
    """99900 → '₹999', 14990050 → '₹1,49,900.50' (Indian digit grouping)."""
    rupees, remainder = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"₹{digits}.{remainder:02d}" if remainder else f"₹{digits}"


def format_amount(paise: int) -> str:
    return "Free" if paise == 0 else format_inr(paise)


def to_local(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo(get_settings().timezone))


def format_date(value: datetime) -> str:
    return to_local(value).strftime("%a, %d %b %Y")


def format_time(value: datetime) -> str:
    return to_local(value).strftime("%I:%M %p")


def registration(user: User) -> RenderedMessage:
    text = f"""Hi {user.name},

Welcome to Skill Cortex! Your account has been created.

Browse upcoming webinars and book your seat: {get_settings().frontend_url}/webinars

{SIGN_OFF}"""
    return RenderedMessage(subject="Welcome to Skill Cortex", email_text=text)


def booking_confirmed(booking: Booking, payment: Payment | None) -> RenderedMessage:
    values = _booking_values(booking, payment)
    text = f"""Hi {values['name']},

Your booking is confirmed.

Webinar: {values['webinar']}
Date: {values['date']}
Time: {values['time_range']}
Amount paid: {values['amount']}
Booking ID: {values['booking_id']}
Payment reference: {values['payment_ref']}

We'll remind you before the session. View your booking: {get_settings().frontend_url}/bookings/{booking.id}

{SIGN_OFF}"""
    sms = (
        f"Skill Cortex: Booking {values['booking_id']} confirmed for {values['webinar']} on "
        f"{values['date']} at {values['time']} IST. Amount: {values['amount']}."
    )
    return RenderedMessage(
        subject=f"Booking confirmed: {values['webinar']} ({values['booking_id']})",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
    )


def admin_payment(booking: Booking, payment: Payment) -> RenderedMessage:
    values = _booking_values(booking, payment)
    user = booking.user
    text = f"""New payment received

User: {user.name}
Email: {user.email}
Phone: {user.phone}
Course: {values['webinar']}
Slot: {values['date']}, {values['time_range']}{" (date & time chosen by the learner)" if booking.slot.set_by_user_id else ""}
Amount: {values['amount']}
Status: PAID
Booking ID: {values['booking_id']}
Payment reference: {values['payment_ref']}"""
    sms = (
        f"Skill Cortex: {values['amount']} received from {user.name} for {values['webinar']} "
        f"({values['date']} {values['time']} IST). Booking {values['booking_id']}."
    )
    return RenderedMessage(
        subject=f"New payment received: {values['amount']} for {values['booking_id']}",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
    )


def booking_cancelled(booking: Booking, *, refunded: bool) -> RenderedMessage:
    values = _booking_values(booking, None)
    refund_line = (
        f"A full refund of {values['amount']} has been initiated to your original payment method. "
        "Refunds usually reach you within 5–7 working days."
        if refunded
        else "No payment was taken for this booking."
    )
    text = f"""Hi {values['name']},

Your booking {values['booking_id']} for {values['webinar']} on {values['date']} at {values['time']} IST has been cancelled by Skill Cortex.

{refund_line}

We're sorry for the inconvenience. You can book another session here: {get_settings().frontend_url}/webinars

{SIGN_OFF}"""
    sms = f"Skill Cortex: Booking {values['booking_id']} for {values['webinar']} on {values['date']} was cancelled." + (
        f" Refund of {values['amount']} initiated." if refunded else ""
    )
    return RenderedMessage(
        subject=f"Booking cancelled: {values['webinar']} ({values['booking_id']})",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
    )


def payment_refunded(booking: Booking, payment: Payment) -> RenderedMessage:
    values = _booking_values(booking, payment)
    text = f"""Hi {values['name']},

We received your payment of {values['amount']} for {values['webinar']} ({values['date']}, {values['time']} IST), but it completed after your seat hold expired and the slot filled up in the meantime.

A full refund of {values['amount']} has been initiated (payment reference {values['payment_ref']}). Refunds usually reach you within 5–7 working days.

Please choose another slot: {get_settings().frontend_url}/webinars

{SIGN_OFF}"""
    sms = f"Skill Cortex: Your payment of {values['amount']} for {values['webinar']} is being refunded as the slot filled up."
    return RenderedMessage(
        subject=f"Refund initiated: {values['webinar']} ({values['booking_id']})",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
    )


def reminder(booking: Booking, offset_days: int) -> RenderedMessage:
    """PRD FR-12 wording: 'is in 3 days' / 'is tomorrow at 10:00 AM' / 'starts today at 10:00 AM'."""
    values = _booking_values(booking, None)
    if offset_days == 0:
        when = f"starts today at {values['time']} IST"
    elif offset_days == 1:
        when = f"is tomorrow at {values['time']} IST"
    else:
        when = f"is in {offset_days} days ({values['date']}, {values['time']} IST)"
    text = f"""Hi {values['name']},

Reminder: your {values['webinar']} webinar {when}.

Date: {values['date']}
Time: {values['time_range']}
Booking ID: {values['booking_id']}

View your booking: {get_settings().frontend_url}/bookings/{booking.id}

{SIGN_OFF}"""
    return RenderedMessage(
        subject=f"Reminder: {values['webinar']} {when}",
        email_text=text,
        sms_text=f"Skill Cortex reminder: Your {values['webinar']} webinar {when}. Booking {values['booking_id']}.",
        variables=_sms_variables(values) | {"when": when},
    )


def password_reset(name: str, link: str) -> RenderedMessage:
    minutes = get_settings().password_reset_minutes
    text = f"""Hi {name},

We received a request to reset your Skill Cortex password. Use this link within {minutes} minutes:

{link}

If you didn't ask for this, you can ignore this email — your password won't change.

{SIGN_OFF}"""
    return RenderedMessage(subject="Reset your Skill Cortex password", email_text=text)


def _booking_values(booking: Booking, payment: Payment | None) -> dict[str, str]:
    slot = booking.slot
    return {
        "name": booking.user.name,
        "webinar": booking.webinar.title,
        "date": format_date(slot.start_at),
        "time": format_time(slot.start_at),
        "time_range": f"{format_time(slot.start_at)} – {format_time(slot.end_at)} IST",
        "amount": format_amount(booking.amount_paise),
        "booking_id": booking.reference,
        "payment_ref": (payment.razorpay_payment_id if payment else None) or "—",
    }


def _sms_variables(values: dict[str, str]) -> dict[str, str]:
    keys = ("name", "webinar", "date", "time", "amount", "booking_id", "payment_ref")
    return {key: values[key] for key in keys}
