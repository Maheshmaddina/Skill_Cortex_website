"""Email and SMS delivery providers (decision D12).

Providers raise `NotificationDeliveryError` on failure; the dispatcher records it and retries.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from functools import lru_cache
from typing import Protocol

import httpx

from app.config import get_settings

logger = logging.getLogger("uvicorn.error")

MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow"


class NotificationDeliveryError(Exception):
    pass


class EmailProvider(Protocol):
    def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class SmsProvider(Protocol):
    def send(self, *, to: str, text: str, template_key: str, variables: dict[str, str]) -> None: ...


class ConsoleEmailProvider:
    def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        logger.warning("[dev email] to=%s subject=%r\n%s", to, subject, text)


class ConsoleSmsProvider:
    def send(self, *, to: str, text: str, template_key: str, variables: dict[str, str]) -> None:
        logger.warning("[dev sms] to=%s template=%s: %s", to, template_key, text)


class SmtpEmailProvider:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        from_address: str,
        from_name: str,
        timeout: float = 10.0,
    ) -> None:
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._use_tls = use_tls
        self._from = formataddr((from_name, from_address))
        self._timeout = timeout

    def send(self, *, to: str, subject: str, text: str, html: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationDeliveryError(f"SMTP delivery failed: {exc}") from exc


class Msg91SmsProvider:
    """MSG91 flow API. `templates` maps a notification type (e.g. "BOOKING_CONFIRMATION") to a
    DLT-approved MSG91 template id whose variables match the notification payload keys."""

    def __init__(
        self,
        *,
        auth_key: str,
        templates: dict[str, str],
        country_code: str = "91",
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._auth_key = auth_key
        self._templates = {key: value for key, value in templates.items() if value}
        self._country_code = country_code
        self._timeout = timeout
        self._transport = transport

    def send(self, *, to: str, text: str, template_key: str, variables: dict[str, str]) -> None:
        template_id = self._templates.get(template_key)
        if not self._auth_key or not template_id:
            raise NotificationDeliveryError(f"No MSG91 template configured for {template_key}.")
        body = {
            "template_id": template_id,
            "short_url": "0",
            "recipients": [{"mobiles": f"{self._country_code}{to}", **variables}],
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    MSG91_FLOW_URL, json=body, headers={"authkey": self._auth_key, "accept": "application/json"}
                )
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"MSG91 request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.is_error or data.get("type") == "error":
            raise NotificationDeliveryError(f"MSG91 rejected the SMS: {data.get('message') or response.status_code}")


@dataclass(frozen=True)
class NotificationProviders:
    email: EmailProvider
    sms: SmsProvider


@lru_cache
def get_notification_providers() -> NotificationProviders:
    settings = get_settings()
    email: EmailProvider = ConsoleEmailProvider()
    if settings.email_provider == "smtp":
        email = SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_address=settings.email_from,
            from_name=settings.email_from_name,
        )
    sms: SmsProvider = ConsoleSmsProvider()
    if settings.sms_provider == "msg91":
        sms = Msg91SmsProvider(
            auth_key=settings.msg91_auth_key,
            templates={
                "BOOKING_CONFIRMATION": settings.msg91_template_booking_confirmation,
                "ADMIN_PAYMENT": settings.msg91_template_admin_payment,
                "CANCELLATION": settings.msg91_template_cancellation,
                "REFUND": settings.msg91_template_refund,
                "REMINDER": settings.msg91_template_reminder,
            },
        )
    return NotificationProviders(email=email, sms=sms)
