"""Password hashing and JWT helpers."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

JWT_ALGORITHM = "HS256"  # pinned; never read from config to prevent downgrade
REFRESH_TOKEN_EXPIRE_DAYS = 7
ACCESS = "access"
REFRESH = "refresh"
OAUTH_STATE = "oauth_state"


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plain password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _encode(claims: dict[str, Any], expires: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    payload = {
        **claims,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    """Create a short-lived access token for the user."""
    return _encode(
        {"sub": str(user_id)}, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), ACCESS
    )


def create_refresh_token(user_id: int) -> str:
    """Create a long-lived refresh token for the user."""
    return _encode({"sub": str(user_id)}, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), REFRESH)


def create_state_token(nonce: str) -> str:
    """Create a signed, short-lived OAuth state token."""
    return _encode({"nonce": nonce}, timedelta(minutes=10), OAUTH_STATE)


def decode_token(token: str, expected_type: str) -> dict[str, Any] | None:
    """Decode and validate a token of the expected type; None if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def hash_token(token: str) -> str:
    """SHA-256 hex digest used to store refresh tokens at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
