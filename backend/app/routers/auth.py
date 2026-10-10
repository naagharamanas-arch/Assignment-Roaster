"""Authentication endpoints (mounted under /api/v1)."""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.auth import oauth
from app.config import settings
from app.dependencies import get_current_user, get_db
from app.exceptions import AppError
from app.models import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UpdateProfileRequest,
    UserResponse,
)
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)
_DEV_ENVIRONMENTS = {"dev", "development", "test", "testing", "local"}


def _redirect_uri() -> str:
    """Google redirect URI built from configuration, never from the request Host."""
    return f"{settings.API_BASE_URL.rstrip('/')}/api/v1/auth/google/callback"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(
    request: Request, body: RegisterRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    """Create an account and return tokens."""
    return auth_service.register_user(db, body)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(
    request: Request, body: LoginRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    """Authenticate with email and password."""
    return auth_service.authenticate(db, body.email, body.password)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Rotate the refresh token and issue a new pair."""
    return auth_service.refresh_session(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: Session = Depends(get_db)) -> Response:
    """Revoke the given refresh token."""
    auth_service.logout(db, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def read_me(user: User = Depends(get_current_user)) -> User:
    """Return the current user's profile."""
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Update the current user's profile."""
    return auth_service.update_profile(db, user, body.full_name)


@router.get("/google")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's consent screen."""
    if not oauth.is_configured():
        raise AppError("Google OAuth is not configured")
    url, nonce = oauth.build_authorization(_redirect_uri())
    response = RedirectResponse(url)
    response.set_cookie(
        oauth.STATE_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT.lower() not in _DEV_ENVIRONMENTS,
    )
    return response


def _login_error(code: str) -> RedirectResponse:
    """Send the browser back to the SPA login page with a short error code."""
    response = RedirectResponse(
        f"{settings.APP_BASE_URL}/login?{urlencode({'error': code})}",
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie(oauth.STATE_COOKIE)
    return response


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle Google's redirect; verify state, sign the user in, return to the SPA."""
    if error:
        logger.warning("Google returned an error: %s", error)
        return _login_error("oauth_cancelled" if error == "access_denied" else "oauth_failed")
    cookie_nonce = request.cookies.get(oauth.STATE_COOKIE)
    if not code or not oauth.verify_state(state, cookie_nonce):
        return _login_error("oauth_state")
    try:
        profile = await oauth.fetch_google_profile(code, _redirect_uri())
    except oauth.OAuthError as exc:
        logger.warning("Google OAuth failed: %s", exc)
        return _login_error("oauth_failed")
    user = auth_service.get_or_create_google_user(db, profile["email"], profile.get("name"))
    if not user.is_active:
        return _login_error("account_disabled")
    tokens = auth_service.issue_tokens(db, user)
    fragment = urlencode(
        {"access_token": tokens.access_token, "refresh_token": tokens.refresh_token}
    )
    response = RedirectResponse(
        f"{settings.APP_BASE_URL}/auth/callback#{fragment}", status_code=status.HTTP_302_FOUND
    )
    response.delete_cookie(oauth.STATE_COOKIE)
    return response
