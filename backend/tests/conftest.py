import os

# Configure the app for tests before anything imports app.config / app.database.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://skill_cortex:skill_cortex@localhost:5432/skill_cortex_test"
)
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough-for-hs256-0123456789"
os.environ["BCRYPT_ROUNDS"] = "4"  # fast hashing in tests
os.environ["APP_ENV"] = "test"
os.environ["RAZORPAY_KEY_ID"] = "rzp_test_dummykey"
os.environ["RAZORPAY_KEY_SECRET"] = "test-razorpay-key-secret"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test-razorpay-webhook-secret"
os.environ["ADMIN_NOTIFY_EMAILS"] = "ops@skillcortex.in, owner@skillcortex.in"
os.environ["ADMIN_NOTIFY_PHONES"] = "9000000001"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["SMS_PROVIDER"] = "console"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # tests that exercise limits turn them on explicitly

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.database import engine as app_engine
from app.database import get_db
from app.main import app
from app.models import UserRole
from app.services.notifications import get_notification_dispatcher
from app.services.razorpay import get_payment_gateway
from tests.factories import auth_header, make_user
from tests.fakes import FakeNotifier, FakeRazorpay

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")
    yield app_engine


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Session bound to an outer transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def razorpay() -> FakeRazorpay:
    return FakeRazorpay()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def client(db: Session, razorpay: FakeRazorpay, notifier: FakeNotifier) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_payment_gateway] = lambda: razorpay  # never call real Razorpay from tests
    # Background delivery would use its own DB session, outside the rolled-back test transaction.
    app.dependency_overrides[get_notification_dispatcher] = lambda: notifier
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers(db: Session) -> dict[str, str]:
    return auth_header(make_user(db, role=UserRole.ADMIN))


@pytest.fixture
def learner_headers(db: Session) -> dict[str, str]:
    return auth_header(make_user(db))
