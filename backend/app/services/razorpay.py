"""Razorpay gateway: a thin HTTP client plus signature checks.

Routes depend on `get_payment_gateway`, so tests substitute a fake gateway.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.services.errors import ServiceError

logger = logging.getLogger("uvicorn.error")


class PaymentGatewayError(ServiceError):
    status_code = 502
    message = "The payment service is temporarily unavailable. Please try again."


class PaymentsNotConfigured(ServiceError):
    status_code = 503
    message = "Online payments are not configured yet."


@dataclass(frozen=True)
class RazorpayOrder:
    id: str
    amount_paise: int
    currency: str


class PaymentGateway(Protocol):
    def create_order(self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]) -> RazorpayOrder: ...

    def refund_payment(self, *, payment_id: str, amount_paise: int, notes: dict[str, str]) -> str:
        """Issue a full/partial refund and return the Razorpay refund id."""
        ...


class HttpRazorpayClient:
    def __init__(
        self,
        key_id: str,
        key_secret: str,
        *,
        base_url: str = "https://api.razorpay.com/v1",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._base_url = base_url
        self._timeout = timeout
        self._transport = transport

    def create_order(self, *, amount_paise: int, currency: str, receipt: str, notes: dict[str, str]) -> RazorpayOrder:
        data = self._post("/orders", {"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes})
        return RazorpayOrder(id=data["id"], amount_paise=data["amount"], currency=data["currency"])

    def refund_payment(self, *, payment_id: str, amount_paise: int, notes: dict[str, str]) -> str:
        data = self._post(f"/payments/{payment_id}/refund", {"amount": amount_paise, "speed": "normal", "notes": notes})
        return data["id"]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not (self._key_id and self._key_secret):
            raise PaymentsNotConfigured
        try:
            with httpx.Client(
                base_url=self._base_url,
                auth=(self._key_id, self._key_secret),
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.post(path, json=payload)
        except httpx.HTTPError as exc:
            logger.error("Razorpay request to %s failed: %s", path, exc)
            raise PaymentGatewayError from exc
        if response.is_error:
            logger.error("Razorpay %s returned %s: %s", path, response.status_code, response.text[:500])
            raise PaymentGatewayError
        return response.json()


@lru_cache
def get_payment_gateway() -> PaymentGateway:
    settings = get_settings()
    return HttpRazorpayClient(
        settings.razorpay_key_id, settings.razorpay_key_secret, base_url=settings.razorpay_api_base
    )


def is_valid_checkout_signature(order_id: str, payment_id: str, signature: str, key_secret: str) -> bool:
    """Checkout returns HMAC-SHA256(order_id|payment_id, key_secret)."""
    if not key_secret:
        return False
    return hmac.compare_digest(_hmac_sha256(key_secret, f"{order_id}|{payment_id}".encode()), signature)


def is_valid_webhook_signature(body: bytes, signature: str, webhook_secret: str) -> bool:
    """Webhooks carry X-Razorpay-Signature = HMAC-SHA256(raw body, webhook secret)."""
    if not webhook_secret:
        return False
    return hmac.compare_digest(_hmac_sha256(webhook_secret, body), signature)


def _hmac_sha256(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
