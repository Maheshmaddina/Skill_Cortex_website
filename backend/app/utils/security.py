import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import bcrypt
import jwt

from app.config import get_settings
from app.models import UserRole

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
BCRYPT_MAX_BYTES = 72


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


@lru_cache
def _dummy_password_hash() -> str:
    return hash_password("timing-equaliser-password-1")


def burn_password_check(password: str) -> None:
    """Spend a bcrypt check's worth of time so unknown emails aren't distinguishable by latency."""
    verify_password(password, _dummy_password_hash())


def create_access_token(user_id: UUID, role: UserRole) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    settings = get_settings()
    expires_in = settings.access_token_minutes * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> UUID:
    """Return the user id from a valid access token. The role claim is informational; callers use the DB role."""
    try:
        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    if payload["type"] != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError
    try:
        return UUID(payload["sub"])
    except ValueError as exc:
        raise InvalidTokenError from exc


def generate_opaque_token() -> tuple[str, str]:
    """Return (raw token for the client, sha256 hash for the database)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
