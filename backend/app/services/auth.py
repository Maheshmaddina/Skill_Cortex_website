"""Registration, login, refresh-token rotation and password reset (decision D11).

Services flush but never commit; routes own the transaction.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, RefreshToken, User
from app.services.departments import get_active_department
from app.services.errors import Conflict, ServiceError
from app.services.notifications import notify_registration
from app.utils.security import (
    burn_password_check,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)


REFRESH_REUSE_GRACE = timedelta(seconds=30)


class EmailAlreadyRegistered(Conflict):
    message = "An account with this email already exists."


class InvalidCredentials(ServiceError):
    status_code = 401
    message = "Email or password is incorrect."


class AccountDisabled(ServiceError):
    status_code = 403
    message = "This account has been disabled."


class InvalidRefreshToken(ServiceError):
    status_code = 401
    message = "Your session has expired. Please log in again."


class InvalidResetToken(ServiceError):
    message = "This password reset link is invalid or has expired."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))


def register_user(
    db: Session, *, name: str, email: str, phone: str, password: str, department_id: UUID
) -> User:
    department = get_active_department(db, department_id)
    if get_user_by_email(db, email) is not None:
        raise EmailAlreadyRegistered

    user = User(
        name=name,
        email=normalize_email(email),
        phone=phone,
        password_hash=hash_password(password),
        department=department,
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as exc:  # lost a race with a concurrent registration
        raise EmailAlreadyRegistered from exc
    notify_registration(db, user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None:
        burn_password_check(password)
        raise InvalidCredentials
    if not verify_password(password, user.password_hash):
        raise InvalidCredentials
    if not user.is_active:
        raise AccountDisabled
    return user


def issue_refresh_token(db: Session, user: User) -> str:
    raw, token_hash = generate_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days)
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.flush()
    return raw


def rotate_refresh_token(db: Session, raw: str) -> tuple[User, str]:
    """Revoke the presented token and issue a new one.

    Replaying an already-revoked token suggests it was stolen, so every session for that
    user is ended. A replay within a few seconds of the rotation is treated as a benign race
    (two browser tabs refreshing at once): it is refused, but other sessions are left alone.
    Callers must commit even when this raises, to persist any revocation.
    """
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update())
    if token is None:
        raise InvalidRefreshToken

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        if now - token.revoked_at > REFRESH_REUSE_GRACE:
            revoke_all_refresh_tokens(db, token.user_id, now)
        raise InvalidRefreshToken
    if token.expires_at <= now:
        raise InvalidRefreshToken

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshToken

    token.revoked_at = now
    return user, issue_refresh_token(db, user)


def revoke_refresh_token(db: Session, raw: str) -> None:
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw), RefreshToken.revoked_at.is_(None))
    )
    if token is not None:
        token.revoked_at = datetime.now(UTC)
        db.flush()


def create_password_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Return (user, raw token), or None when no active account matches (callers must not reveal which)."""
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None

    now = datetime.now(UTC)
    # Only the most recent reset link stays usable.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw, token_hash = generate_opaque_token()
    expires_at = now + timedelta(minutes=get_settings().password_reset_minutes)
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.flush()
    return user, raw


def reset_password(db: Session, raw: str, new_password: str) -> User:
    token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw)).with_for_update()
    )
    now = datetime.now(UTC)
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise InvalidResetToken

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise InvalidResetToken

    user.password_hash = hash_password(new_password)
    token.used_at = now
    revoke_all_refresh_tokens(db, user.id, now)
    db.flush()
    return user


def revoke_all_refresh_tokens(db: Session, user_id: UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
