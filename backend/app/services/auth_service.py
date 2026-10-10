"""Business logic for authentication."""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.jwt import (
    REFRESH,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.exceptions import AppError, ConflictError, ForbiddenError
from app.models import RefreshToken, User
from app.schemas.auth import AuthResponse, RegisterRequest, UserResponse

logger = logging.getLogger(__name__)

# Used to equalise timing when the account does not exist or has no password.
_DUMMY_HASH = hash_password("timing-equaliser-password")


class UnauthorizedError(AppError):
    """Authentication failed (401)."""

    status_code = 401
    default_detail = "Invalid credentials"


def _aware(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite) as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by (case-insensitive) email."""
    return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()


def issue_tokens(db: Session, user: User) -> AuthResponse:
    """Create an access/refresh pair and persist the hashed refresh token."""
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token=hash_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return AuthResponse(
        access_token=create_access_token(user.id),
        refresh_token=refresh,
        user=UserResponse.model_validate(user),
    )


def register_user(db: Session, data: RegisterRequest) -> AuthResponse:
    """Create an email/password user and sign them in."""
    if get_user_by_email(db, data.email) is not None:
        raise ConflictError("Email already registered")
    user = User(
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User registered id=%s", user.id)
    return issue_tokens(db, user)


def authenticate(db: Session, email: str, password: str) -> AuthResponse:
    """Verify credentials and return tokens."""
    user = get_user_by_email(db, email)
    hashed = user.hashed_password if user and user.hashed_password else _DUMMY_HASH
    valid = verify_password(password, hashed)
    if user is None or not user.hashed_password or not valid:
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")
    return issue_tokens(db, user)


# Grace window in which re-presenting a just-rotated token is a benign race, not theft.
REFRESH_GRACE_SECONDS = 20.0
_rotated_at: dict[str, float] = {}
_rotation_lock = threading.Lock()


def _mark_rotated(token_hash: str) -> None:
    now = time.monotonic()
    for key in [k for k, t in _rotated_at.items() if now - t > 300]:
        del _rotated_at[key]
    _rotated_at[token_hash] = now


def _recently_rotated(token_hash: str) -> bool:
    rotated = _rotated_at.get(token_hash)
    return rotated is not None and time.monotonic() - rotated <= REFRESH_GRACE_SECONDS


def _revoke_all(db: Session, user_id: int) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    db.commit()


def refresh_session(db: Session, refresh_token: str) -> AuthResponse:
    """Rotate a refresh token: revoke the old one and issue a new pair."""
    payload = decode_token(refresh_token, REFRESH)
    if payload is None:
        raise UnauthorizedError("Invalid or expired refresh token")
    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token == hash_token(refresh_token))
    ).scalar_one_or_none()
    if stored is None:
        raise UnauthorizedError("Invalid refresh token")
    if stored.revoked:
        return _handle_reuse(db, stored.user_id, stored.token)
    if _aware(stored.expires_at) <= datetime.now(UTC):
        raise UnauthorizedError("Refresh token expired")
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    # Atomic compare-and-set: only one concurrent request can flip revoked.
    with _rotation_lock:
        result = db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == stored.id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )
        won = bool(getattr(result, "rowcount", 0))
        if won:
            _mark_rotated(stored.token)
    if not won:
        db.rollback()
        return _handle_reuse(db, stored.user_id, stored.token)
    db.commit()
    return issue_tokens(db, user)


def _handle_reuse(db: Session, user_id: int, token_hash: str) -> AuthResponse:
    """Reject a token that was already rotated; revoke every session unless in grace."""
    if _recently_rotated(token_hash):
        # Benign race (parallel tabs / retries): reject without killing sessions.
        raise UnauthorizedError("Refresh token already used")
    logger.warning("Refresh token reuse detected user_id=%s", user_id)
    _revoke_all(db, user_id)
    raise UnauthorizedError("Refresh token revoked")


def logout(db: Session, refresh_token: str) -> None:
    """Revoke a refresh token (idempotent)."""
    stored = db.execute(
        select(RefreshToken).where(RefreshToken.token == hash_token(refresh_token))
    ).scalar_one_or_none()
    if stored is not None and not stored.revoked:
        stored.revoked = True
        db.commit()


def update_profile(db: Session, user: User, full_name: str | None) -> User:
    """Update the user's profile fields."""
    user.full_name = full_name
    db.commit()
    db.refresh(user)
    return user


def get_or_create_google_user(db: Session, email: str, full_name: str | None) -> User:
    """Return the user for a verified Google email, creating or linking as needed."""
    user = get_user_by_email(db, email)
    if user is None:
        user = User(
            email=email.lower(),
            full_name=full_name,
            oauth_provider="google",
            is_verified=True,
        )
        db.add(user)
    else:
        if not user.is_verified and user.hashed_password:
            # Pre-hijack defence: the password may have been set by someone who never
            # proved ownership of this email. Drop it and kill any sessions it created.
            logger.warning("Unverified password account claimed via Google user_id=%s", user.id)
            user.hashed_password = None
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
                .values(revoked=True)
            )
        if user.oauth_provider is None:
            user.oauth_provider = "google"
        user.is_verified = True
        if not user.full_name and full_name:
            user.full_name = full_name
    db.commit()
    db.refresh(user)
    return user
