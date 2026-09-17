import json
import smtplib

import httpx
import pytest

from app.services.notification_providers import (
    MSG91_FLOW_URL,
    ConsoleEmailProvider,
    ConsoleSmsProvider,
    Msg91SmsProvider,
    NotificationDeliveryError,
    SmtpEmailProvider,
    get_notification_providers,
)


def test_msg91_sends_the_dlt_template_with_variables() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), authkey=request.headers["authkey"], body=json.loads(request.content))
        return httpx.Response(200, json={"type": "success", "message": "queued"})

    provider = Msg91SmsProvider(
        auth_key="msg91-key", templates={"BOOKING_CONFIRMATION": "tpl_booking"}, transport=httpx.MockTransport(handler)
    )
    provider.send(
        to="9876543210",
        text="(rendered by the template)",
        template_key="BOOKING_CONFIRMATION",
        variables={"booking_id": "SC-10001", "webinar": "Python"},
    )

    assert seen["url"] == MSG91_FLOW_URL
    assert seen["authkey"] == "msg91-key"
    assert seen["body"] == {
        "template_id": "tpl_booking",
        "short_url": "0",
        "recipients": [{"mobiles": "919876543210", "booking_id": "SC-10001", "webinar": "Python"}],
    }


@pytest.mark.parametrize(
    "status_code, body",
    [(200, {"type": "error", "message": "Invalid template"}), (401, {"message": "Unauthorized"})],
)
def test_msg91_rejections_are_delivery_errors(status_code: int, body: dict) -> None:
    provider = Msg91SmsProvider(
        auth_key="key",
        templates={"REMINDER": "tpl"},
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json=body)),
    )

    with pytest.raises(NotificationDeliveryError):
        provider.send(to="9876543210", text="x", template_key="REMINDER", variables={})


def test_msg91_needs_a_template_for_each_message_type() -> None:
    provider = Msg91SmsProvider(auth_key="key", templates={"BOOKING_CONFIRMATION": ""})

    with pytest.raises(NotificationDeliveryError, match="No MSG91 template"):
        provider.send(to="9876543210", text="x", template_key="BOOKING_CONFIRMATION", variables={})


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_with: Exception | None = None

    def __init__(self, host: str, port: int, timeout: float) -> None:
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.calls: list = [("connect", host, port)]
        self.messages: list = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def starttls(self, context) -> None:
        self.calls.append("starttls")

    def login(self, username: str, password: str) -> None:
        self.calls.append(("login", username))

    def send_message(self, message) -> None:
        self.messages.append(message)


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances, FakeSMTP.fail_with = [], None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def smtp_provider() -> SmtpEmailProvider:
    return SmtpEmailProvider(
        host="smtp.example.com",
        port=587,
        username="apikey",
        password="secret",
        use_tls=True,
        from_address="no-reply@skillcortex.in",
        from_name="Skill Cortex",
    )


def test_smtp_provider_sends_over_starttls(fake_smtp: type[FakeSMTP]) -> None:
    smtp_provider().send(to="learner@example.com", subject="Booking confirmed", text="Hello")

    [smtp] = fake_smtp.instances
    assert smtp.calls == [("connect", "smtp.example.com", 587), "starttls", ("login", "apikey")]
    [message] = smtp.messages
    assert message["From"] == "Skill Cortex <no-reply@skillcortex.in>"
    assert (message["To"], message["Subject"]) == ("learner@example.com", "Booking confirmed")
    assert message.get_content().strip() == "Hello"


def test_smtp_provider_sends_html_with_a_plain_text_fallback(fake_smtp: type[FakeSMTP]) -> None:
    smtp_provider().send(to="learner@example.com", subject="Receipt", text="Plain receipt", html="<p>HTML receipt</p>")

    [message] = fake_smtp.instances[0].messages
    assert message.get_content_type() == "multipart/alternative"
    assert message.get_body(("plain",)).get_content().strip() == "Plain receipt"
    assert message.get_body(("html",)).get_content().strip() == "<p>HTML receipt</p>"


def test_smtp_connection_failures_are_delivery_errors(fake_smtp: type[FakeSMTP]) -> None:
    fake_smtp.fail_with = ConnectionRefusedError("refused")

    with pytest.raises(NotificationDeliveryError, match="SMTP delivery failed"):
        smtp_provider().send(to="learner@example.com", subject="s", text="t")


def test_development_defaults_to_console_providers() -> None:
    providers = get_notification_providers()

    assert isinstance(providers.email, ConsoleEmailProvider)
    assert isinstance(providers.sms, ConsoleSmsProvider)
