import base64
import hashlib
import hmac
import json

import httpx
import pytest

from app.services.razorpay import (
    HttpRazorpayClient,
    PaymentGatewayError,
    PaymentsNotConfigured,
    is_valid_checkout_signature,
    is_valid_webhook_signature,
)


def test_checkout_signature_matches_razorpay_scheme() -> None:
    expected = hmac.new(b"secret", b"order_ABC|pay_XYZ", hashlib.sha256).hexdigest()

    assert is_valid_checkout_signature("order_ABC", "pay_XYZ", expected, "secret")
    assert not is_valid_checkout_signature("order_ABC", "pay_OTHER", expected, "secret")
    assert not is_valid_checkout_signature("order_ABC", "pay_XYZ", expected, "")


def test_webhook_signature_covers_the_raw_body() -> None:
    body = b'{"event":"payment.captured"}'
    signature = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()

    assert is_valid_webhook_signature(body, signature, "whsec")
    assert not is_valid_webhook_signature(body + b" ", signature, "whsec")


def make_client(handler) -> HttpRazorpayClient:
    return HttpRazorpayClient("rzp_test_key", "key_secret", transport=httpx.MockTransport(handler))


def test_create_order_calls_the_orders_api() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), auth=request.headers["authorization"], body=json.loads(request.content))
        return httpx.Response(200, json={"id": "order_ABC", "amount": 99_900, "currency": "INR"})

    order = make_client(handler).create_order(
        amount_paise=99_900, currency="INR", receipt="SC-10001", notes={"booking_id": "b1"}
    )

    assert (order.id, order.amount_paise, order.currency) == ("order_ABC", 99_900, "INR")
    assert seen["url"] == "https://api.razorpay.com/v1/orders"
    assert seen["auth"] == "Basic " + base64.b64encode(b"rzp_test_key:key_secret").decode()
    assert seen["body"] == {"amount": 99_900, "currency": "INR", "receipt": "SC-10001", "notes": {"booking_id": "b1"}}


def test_refund_calls_the_payment_refund_api() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), body=json.loads(request.content))
        return httpx.Response(200, json={"id": "rfnd_123"})

    refund_id = make_client(handler).refund_payment(payment_id="pay_XYZ", amount_paise=99_900, notes={})

    assert refund_id == "rfnd_123"
    assert seen["url"] == "https://api.razorpay.com/v1/payments/pay_XYZ/refund"
    assert seen["body"]["amount"] == 99_900


def test_gateway_errors_are_translated() -> None:
    rejected = make_client(lambda request: httpx.Response(400, json={"error": {"description": "bad"}}))

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(PaymentGatewayError):
        rejected.create_order(amount_paise=1, currency="INR", receipt="r", notes={})
    with pytest.raises(PaymentGatewayError):
        make_client(unreachable).refund_payment(payment_id="pay_1", amount_paise=1, notes={})


def test_missing_keys_mean_payments_are_not_configured() -> None:
    with pytest.raises(PaymentsNotConfigured):
        HttpRazorpayClient("", "").create_order(amount_paise=1, currency="INR", receipt="r", notes={})
