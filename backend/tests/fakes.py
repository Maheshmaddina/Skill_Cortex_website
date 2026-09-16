"""Test doubles: an in-memory Razorpay gateway, notification providers/dispatcher, and signature helpers."""

import hashlib
import hmac
import json
import uuid
from uuid import UUID

from app.config import get_settings
from app.services.razorpay import PaymentGatewayError, RazorpayOrder


class FakeRazorpay:
    def __init__(self) -> None:
        self.orders: list[dict] = []
        self.refunds: list[dict] = []
        self.fail_refunds = False

    def create_order(self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]) -> RazorpayOrder:
        order = {"id": f"order_{uuid.uuid4().hex[:14]}", "amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes}
        self.orders.append(order)
        return RazorpayOrder(id=order["id"], amount_paise=amount_paise, currency=currency)

    def refund_payment(self, *, payment_id: str, amount_paise: int, notes: dict[str, str]) -> str:
        if self.fail_refunds:
            raise PaymentGatewayError
        refund = {"id": f"rfnd_{uuid.uuid4().hex[:14]}", "payment_id": payment_id, "amount": amount_paise, "notes": notes}
        self.refunds.append(refund)
        return refund["id"]


class FakeEmailProvider:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.error: Exception | None = None

    def send(self, *, to: str, subject: str, text: str) -> None:
        if self.error:
            raise self.error
        self.sent.append({"to": to, "subject": subject, "text": text})


class FakeSmsProvider:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.error: Exception | None = None

    def send(self, *, to: str, text: str, template_key: str, variables: dict[str, str]) -> None:
        if self.error:
            raise self.error
        self.sent.append({"to": to, "text": text, "template_key": template_key, "variables": variables})


class FakeNotifier:
    """Stands in for NotificationDispatcher in API tests; records what the routes scheduled."""

    def __init__(self) -> None:
        self.dispatch_calls = 0
        self.reset_links: list[str] = []
        self.reset_notification_ids: list[UUID] = []

    def dispatch_pending(self) -> None:
        self.dispatch_calls += 1

    def deliver_password_reset(self, notification_id: UUID, link: str) -> None:
        self.reset_notification_ids.append(notification_id)
        self.reset_links.append(link)


def sign_checkout(order_id: str, payment_id: str) -> str:
    secret = get_settings().razorpay_key_secret.encode()
    return hmac.new(secret, f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def sign_webhook(body: bytes) -> str:
    return hmac.new(get_settings().razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()


def webhook_body(
    event: str,
    *,
    order_id: str,
    payment_id: str = "pay_WEBHOOK01",
    amount_paise: int = 99_900,
    error_description: str | None = None,
) -> bytes:
    entity = {
        "id": payment_id,
        "entity": "payment",
        "order_id": order_id,
        "amount": amount_paise,
        "currency": "INR",
        "status": "failed" if event == "payment.failed" else "captured",
        "error_description": error_description,
    }
    return json.dumps({"entity": "event", "event": event, "payload": {"payment": {"entity": entity}}}).encode()
