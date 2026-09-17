"""Message content for each notification (PRD 8.14–8.16). Times are shown in IST (decision D10)."""

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models import Booking, Payment, PaymentMethod, User

SIGN_OFF = "— Team Skill Cortex"


@dataclass(frozen=True)
class RenderedMessage:
    subject: str
    email_text: str
    sms_text: str = ""
    variables: dict[str, str] = field(default_factory=dict)  # named values for SMS templates
    email_html: str | None = None  # optional HTML version of the email (e.g. a formatted receipt)


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
    """Confirmation for the learner; for a paid booking it carries the payment receipt."""
    values = _booking_values(booking, payment)
    receipt = _receipt_text(booking, payment) if payment else ""
    text = f"""Hi {values['name']},

Your booking is confirmed.

Webinar: {values['webinar']}
Date: {values['date']}
Time: {values['time_range']}
Amount paid: {values['amount']}
Booking ID: {values['booking_id']}
Payment reference: {values['payment_ref']}
{receipt}
We'll remind you before the session. View your booking: {get_settings().frontend_url}/bookings/{booking.id}

{SIGN_OFF}"""
    sms = (
        f"Skill Cortex: Booking {values['booking_id']} confirmed for {values['webinar']} on "
        f"{values['date']} at {values['time']} IST. Amount: {values['amount']}."
    )
    html = (
        _email_html(
            heading="Your booking is confirmed",
            intro=f"Hi {values['name']}, thank you for your payment. Your seat is booked and here is your receipt.",
            booking=booking,
            payment=payment,
            button=("View receipt", f"{get_settings().frontend_url}/bookings/{booking.id}/receipt"),
            footer="We'll remind you before the session.",
        )
        if payment
        else None
    )
    return RenderedMessage(
        subject=f"Booking confirmed: {values['webinar']} ({values['booking_id']})",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
        email_html=html,
    )


def admin_payment(booking: Booking, payment: Payment) -> RenderedMessage:
    values = _booking_values(booking, payment)
    user = booking.user
    learner_chose = " (date & time chosen by the learner)" if booking.slot.set_by_user_id else ""
    text = f"""New payment received

User: {user.name}
Email: {user.email}
Phone: {user.phone}
Course: {values['webinar']}
Slot: {values['date']}, {values['time_range']}{learner_chose}
Amount: {values['amount']}
Status: PAID
Booking ID: {values['booking_id']}
Payment reference: {values['payment_ref']}
{_receipt_text(booking, payment)}"""
    sms = (
        f"Skill Cortex: {values['amount']} received from {user.name} for {values['webinar']} "
        f"({values['date']} {values['time']} IST). Booking {values['booking_id']}."
    )
    return RenderedMessage(
        subject=f"New payment received: {values['amount']} for {values['booking_id']}",
        email_text=text,
        sms_text=sms,
        variables=_sms_variables(values),
        email_html=_email_html(
            heading="New payment received",
            intro=f"{escape(user.name)} paid for a webinar{learner_chose}. The booking is confirmed.",
            booking=booking,
            payment=payment,
            button=("Open bookings in admin", f"{get_settings().frontend_url}/admin/bookings?q={booking.reference}"),
            footer="Copy of the receipt sent to the learner.",
        ),
    )


# --- payment receipt -------------------------------------------------------------


def _payment_method(payment: Payment) -> str:
    return "UPI" if payment.method == PaymentMethod.UPI else "Card / Netbanking / Wallet (Razorpay)"


def _payment_reference(payment: Payment) -> str:
    if payment.method == PaymentMethod.UPI:
        return f"UPI transaction ID {payment.upi_reference}"
    return payment.razorpay_payment_id or "—"


def _receipt_rows(booking: Booking, payment: Payment) -> list[tuple[str, str]]:
    user, slot = booking.user, booking.slot
    paid_at = payment.paid_at or datetime.now().astimezone()
    return [
        ("Receipt no.", booking.reference),
        ("Paid on", f"{format_date(paid_at)}, {format_time(paid_at)} IST"),
        ("Billed to", f"{user.name} · {user.email} · {user.phone}"),
        ("Course", booking.webinar.title),
        ("Session", f"{format_date(slot.start_at)}, {format_time(slot.start_at)} – {format_time(slot.end_at)} IST"),
        ("Amount paid (incl. all taxes)", format_inr(payment.amount_paise)),
        ("Payment method", _payment_method(payment)),
        ("Payment reference", _payment_reference(payment)),
        ("Status", "PAID"),
    ]


def _receipt_text(booking: Booking, payment: Payment) -> str:
    rows = "\n".join(f"{label}: {value}" for label, value in _receipt_rows(booking, payment))
    link = f"{get_settings().frontend_url}/bookings/{booking.id}/receipt"
    return f"""
---------------- PAYMENT RECEIPT ----------------
Skill Cortex AI · SreeNagar Colony, Punganur Road, Madanapalle
{rows}
Printable receipt: {link}
-------------------------------------------------
"""


def _email_html(
    *, heading: str, intro: str, booking: Booking, payment: Payment, button: tuple[str, str], footer: str
) -> str:
    rows = "".join(
        f'<tr><td style="padding:8px 0;color:#64748b;border-bottom:1px solid #f1f5f9">{escape(label)}</td>'
        f'<td style="padding:8px 0;text-align:right;font-weight:600;color:#0f172a;border-bottom:1px solid #f1f5f9">'
        f"{escape(value)}</td></tr>"
        for label, value in _receipt_rows(booking, payment)
    )
    label, url = button
    return f"""<!doctype html>
<html><body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #e2e8f0">
<tr><td style="padding:20px 24px;border-bottom:4px solid #ff6b00">
<span style="font-size:20px;font-weight:700">Skill <span style="color:#ff6b00">Cortex</span> AI</span>
<div style="font-size:12px;color:#64748b">SreeNagar Colony, Punganur Road, Madanapalle</div>
</td></tr>
<tr><td style="padding:24px">
<h1 style="margin:0 0 8px;font-size:22px">{escape(heading)}</h1>
<p style="margin:0 0 20px;color:#475569;line-height:1.5">{intro}</p>
<div style="font-size:12px;font-weight:700;letter-spacing:.05em;color:#64748b;text-transform:uppercase">Payment receipt</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:6px;font-size:14px">{rows}</table>
<p style="margin:24px 0 0;text-align:center">
<a href="{escape(url)}" style="display:inline-block;background:#ff6b00;color:#ffffff;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:10px">{escape(label)}</a>
</p>
<p style="margin:20px 0 0;color:#64748b;font-size:13px;text-align:center">{escape(footer)}</p>
</td></tr>
<tr><td style="padding:14px 24px;background:#021927;color:#94a3b8;font-size:12px;border-radius:0 0 16px 16px">
Computer-generated payment receipt · {escape(get_settings().email_from)} — Team Skill Cortex
</td></tr>
</table></td></tr></table>
</body></html>"""


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
        "payment_ref": (_payment_reference(payment) if payment else None) or "—",
    }


def _sms_variables(values: dict[str, str]) -> dict[str, str]:
    keys = ("name", "webinar", "date", "time", "amount", "booking_id", "payment_ref")
    return {key: values[key] for key in keys}
