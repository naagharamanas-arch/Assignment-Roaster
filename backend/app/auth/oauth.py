"""Google OAuth (authorization-code flow) using authlib.

State is a signed JWT carrying a nonce; the same nonce is stored in an httponly
cookie so the callback can verify the request came from the same browser.
"""

import secrets
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.auth.jwt import OAUTH_STATE, create_state_token, decode_token
from app.config import settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "openid email profile"
STATE_COOKIE = "oauth_state_nonce"


class OAuthError(Exception):
    """Raised when the OAuth handshake fails."""


def is_configured() -> bool:
    """True when Google credentials are set."""
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def _client(redirect_uri: str) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scope=SCOPE,
        redirect_uri=redirect_uri,
    )


def build_authorization(redirect_uri: str) -> tuple[str, str]:
    """Return (authorization_url, nonce). The nonce must be set as a cookie."""
    nonce = secrets.token_urlsafe(24)
    state = create_state_token(nonce)
    url, _ = _client(redirect_uri).create_authorization_url(
        AUTHORIZE_URL, state=state, access_type="online", prompt="select_account"
    )
    return url, nonce


def verify_state(state: str | None, cookie_nonce: str | None) -> bool:
    """Check the state JWT is valid and its nonce matches the cookie."""
    if not state or not cookie_nonce:
        return False
    payload = decode_token(state, OAUTH_STATE)
    if payload is None:
        return False
    return secrets.compare_digest(str(payload.get("nonce", "")), cookie_nonce)


async def fetch_google_profile(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange the code for tokens and return the Google userinfo payload."""
    async with _client(redirect_uri) as client:
        try:
            token = await client.fetch_token(TOKEN_URL, code=code, grant_type="authorization_code")
            response = await client.get(USERINFO_URL, token=token)
            response.raise_for_status()
            profile: dict[str, Any] = response.json()
        except Exception as exc:
            raise OAuthError("Google token exchange failed") from exc
    if not profile.get("email") or not profile.get("email_verified"):
        raise OAuthError("Google account email is not verified")
    return profile
