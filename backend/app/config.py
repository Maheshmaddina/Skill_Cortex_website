from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://skill_cortex:skill_cortex@localhost:5432/skill_cortex"
    # "null" opens a connection per request instead of pooling — for serverless hosts (Vercel) with a pooled Postgres.
    database_pool: Literal["queue", "null"] = "queue"
    timezone: str = "Asia/Kolkata"
    booking_hold_minutes: int = 15
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"  # comma-separated

    # Abuse protection
    rate_limit_enabled: bool = True
    # Header carrying the real client IP, set by a trusted proxy (e.g. "x-real-ip" on Vercel). Empty = socket address.
    client_ip_header: str = ""
    max_request_body_bytes: int = 1_000_000

    # Auth (decision D11)
    jwt_secret: str = DEFAULT_JWT_SECRET
    access_token_minutes: int = 60
    refresh_token_days: int = 7
    password_reset_minutes: int = 30
    bcrypt_rounds: int = 12
    cookie_secure: bool = False  # set true behind HTTPS
    # Must match the public path of the auth routes (e.g. /api/auth when the API is served under /api).
    refresh_cookie_path: str = "/auth"

    # Razorpay (decision D5). Use rzp_test_ keys outside production.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_api_base: str = "https://api.razorpay.com/v1"

    # Direct UPI (QR code / UPI ID): learners pay this UPI ID and submit the UTR; an admin verifies it.
    # Empty hides the option.
    upi_id: str = ""
    upi_payee_name: str = "Skill Cortex"

    # Notifications (decision D12). "console" providers only log — use them in development.
    email_provider: Literal["console", "smtp"] = "console"
    sms_provider: Literal["console", "msg91"] = "console"
    notification_max_attempts: int = 3
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    email_from: str = "no-reply@skillcortex.local"
    email_from_name: str = "Skill Cortex"
    # MSG91 flow API; Indian DLT rules require a pre-approved template per message type.
    msg91_auth_key: str = ""
    msg91_template_booking_confirmation: str = ""
    msg91_template_admin_payment: str = ""
    msg91_template_cancellation: str = ""
    msg91_template_refund: str = ""
    msg91_template_reminder: str = ""

    # Comma-separated admin recipients for payment notifications
    admin_notify_emails: str = ""
    admin_notify_phones: str = ""

    # Bearer token for GET/POST /internal/run-jobs, which runs the background jobs on hosts without the
    # scheduler process (Vercel Cron sends it automatically as CRON_SECRET). Empty disables the endpoint.
    cron_secret: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        # Hosted Postgres (Neon, Vercel) hands out postgres:// or postgresql:// URLs; this app uses psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return _split_csv(self.cors_origins)

    @property
    def admin_notify_email_list(self) -> list[str]:
        return _split_csv(self.admin_notify_emails)

    @property
    def admin_notify_phone_list(self) -> list[str]:
        return _split_csv(self.admin_notify_phones)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _require_safe_production_config(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be a strong value (32+ characters)")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true (the site must be served over HTTPS)")
        if not self.frontend_url.startswith("https://"):
            problems.append("FRONTEND_URL must be an https:// URL (it is used in email links)")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must list the real frontend origin, not '*'")
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED must be true")
        if self.cron_secret and len(self.cron_secret) < 32:
            problems.append("CRON_SECRET must be 32+ characters")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems) + ".")
        return self


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
