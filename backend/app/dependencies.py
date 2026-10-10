"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import ACCESS, decode_token
from app.database import get_db
from app.models import User

__all__ = ["get_db", "get_current_user", "get_current_admin"]

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Return the active user identified by the Bearer access token."""
    if credentials is None:
        raise _unauthorized()
    payload = decode_token(credentials.credentials, ACCESS)
    if payload is None:
        raise _unauthorized("Invalid or expired token")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise _unauthorized("Invalid token") from None
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized("User not found or inactive")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Return the current user, requiring admin rights (403 otherwise)."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
