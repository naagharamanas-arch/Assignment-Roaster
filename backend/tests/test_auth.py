"""Tests for the auth module."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import oauth
from app.auth.jwt import create_access_token, decode_token, hash_password, verify_password
from app.config import settings
from app.dependencies import get_current_admin, get_current_user
from app.models import Base, RefreshToken, User
from app.services import auth_service

BASE = "/api/v1/auth"
CREDS = {"email": "Alice@Example.com", "password": "supersecret1", "full_name": "Alice"}


def _register(client: TestClient) -> dict[str, Any]:
    res = client.post(f"{BASE}/register", json=CREDS)
    assert res.status_code == 201, res.text
    return res.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_password_hashing() -> None:
    hashed = hash_password("pw-12345678")
    assert hashed != "pw-12345678"
    assert verify_password("pw-12345678", hashed)
    assert not verify_password("wrong", hashed)


def test_register_and_duplicate(client: TestClient, db_session: Session) -> None:
    data = _register(client)
    assert data["user"]["email"] == "alice@example.com"
    assert "hashed_password" not in data["user"]
    user = db_session.execute(select(User)).scalar_one()
    assert user.hashed_password and user.hashed_password != CREDS["password"]
    assert client.post(f"{BASE}/register", json=CREDS).status_code == 409


def test_register_validation(client: TestClient) -> None:
    bad = {"email": "x@example.com", "password": "short"}
    assert client.post(f"{BASE}/register", json=bad).status_code == 422
    assert client.post(f"{BASE}/register", json={**bad, "email": "nope"}).status_code == 422


def test_login_success_and_failures(client: TestClient) -> None:
    _register(client)
    login = f"{BASE}/login"
    ok = client.post(login, json={"email": "alice@example.com", "password": "supersecret1"})
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    wrong = client.post(login, json={"email": "alice@example.com", "password": "nope-nope"})
    assert wrong.status_code == 401
    missing = client.post(login, json={"email": "no@example.com", "password": "nope-nope"})
    assert missing.status_code == 401


def test_login_rate_limited(client: TestClient) -> None:
    body = {"email": "a@example.com", "password": "whatever1"}
    codes = [client.post(f"{BASE}/login", json=body).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5
    assert 429 in codes[5:]


def test_me_requires_valid_token(client: TestClient) -> None:
    assert client.get(f"{BASE}/me").status_code == 401
    assert client.get(f"{BASE}/me", headers=_auth("garbage")).status_code == 401
    tokens = _register(client)
    # refresh token must not work as access token
    assert client.get(f"{BASE}/me", headers=_auth(tokens["refresh_token"])).status_code == 401
    res = client.get(f"{BASE}/me", headers=_auth(tokens["access_token"]))
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"


def test_update_me(client: TestClient) -> None:
    tokens = _register(client)
    res = client.put(
        f"{BASE}/me", json={"full_name": "Alice B"}, headers=_auth(tokens["access_token"])
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Alice B"
    assert client.put(f"{BASE}/me", json={"full_name": "x"}).status_code == 401


def test_refresh_rotates_and_revokes_old(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = _register(client)
    old = tokens["refresh_token"]
    res = client.post(f"{BASE}/refresh", json={"refresh_token": old})
    assert res.status_code == 200
    new = res.json()["refresh_token"]
    assert new != old
    assert client.get(f"{BASE}/me", headers=_auth(res.json()["access_token"])).status_code == 200
    # old token is revoked; reuse after the grace window revokes the whole family
    monkeypatch.setattr(auth_service, "REFRESH_GRACE_SECONDS", 0.0)
    assert client.post(f"{BASE}/refresh", json={"refresh_token": old}).status_code == 401
    assert client.post(f"{BASE}/refresh", json={"refresh_token": new}).status_code == 401
    rows = db_session.execute(select(RefreshToken)).scalars().all()
    assert rows and all(r.revoked for r in rows)


def test_refresh_rejects_access_token_and_expired(client: TestClient, db_session: Session) -> None:
    tokens = _register(client)
    assert (
        client.post(f"{BASE}/refresh", json={"refresh_token": tokens["access_token"]}).status_code
        == 401
    )
    row = db_session.execute(select(RefreshToken)).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    res = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    tokens = _register(client)
    res = client.post(f"{BASE}/logout", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 204
    assert (
        client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code
        == 401
    )
    # idempotent
    assert (
        client.post(f"{BASE}/logout", json={"refresh_token": tokens["refresh_token"]}).status_code
        == 204
    )


def test_inactive_user_rejected(client: TestClient, db_session: Session) -> None:
    tokens = _register(client)
    user = db_session.execute(select(User)).scalar_one()
    user.is_active = False
    db_session.commit()
    assert client.get(f"{BASE}/me", headers=_auth(tokens["access_token"])).status_code == 401


def test_admin_dependency(app: FastAPI, client: TestClient, db_session: Session) -> None:
    @app.get("/whoami")
    async def whoami(user: User = Depends(get_current_user)) -> dict[str, int]:
        return {"id": user.id}

    @app.get("/admin-only")
    async def admin_only(user: User = Depends(get_current_admin)) -> dict[str, int]:
        return {"id": user.id}

    tokens = _register(client)
    headers = _auth(tokens["access_token"])
    assert client.get("/whoami", headers=headers).status_code == 200
    assert client.get("/admin-only", headers=headers).status_code == 403
    user = db_session.execute(select(User)).scalar_one()
    user.is_admin = True
    db_session.commit()
    assert client.get("/admin-only", headers=_auth(create_access_token(user.id))).status_code == 200


def _start_google(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(oauth, "is_configured", lambda: True)
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_SECRET", "secret")
    res = client.get(f"{BASE}/google", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers["location"]
    assert location.startswith(oauth.AUTHORIZE_URL)
    assert oauth.STATE_COOKIE in res.cookies
    return parse_qs(urlparse(location).query)["state"][0]


def test_google_flow_creates_user(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_google(client, monkeypatch)

    async def fake_profile(code: str, redirect_uri: str) -> dict[str, Any]:
        return {"email": "Gina@Example.com", "email_verified": True, "name": "Gina"}

    monkeypatch.setattr(oauth, "fetch_google_profile", fake_profile)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert res.status_code == 302
    fragment = parse_qs(urlparse(res.headers["location"]).fragment)
    assert fragment["access_token"] and fragment["refresh_token"]
    user = db_session.execute(select(User)).scalar_one()
    assert user.email == "gina@example.com"
    assert user.oauth_provider == "google"
    assert user.is_verified and user.hashed_password is None
    me = client.get(f"{BASE}/me", headers=_auth(fragment["access_token"][0]))
    assert me.json()["email"] == "gina@example.com"


def test_google_links_existing_user(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(client)
    state = _start_google(client, monkeypatch)

    async def fake_profile(code: str, redirect_uri: str) -> dict[str, Any]:
        return {"email": "alice@example.com", "email_verified": True, "name": "Other"}

    monkeypatch.setattr(oauth, "fetch_google_profile", fake_profile)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert res.status_code == 302
    users = db_session.execute(select(User)).scalars().all()
    assert len(users) == 1
    assert users[0].oauth_provider == "google"
    assert users[0].hashed_password is None  # unverified password is dropped (pre-hijack)
    assert users[0].full_name == "Alice"


def _error_code(res: Any) -> str:
    assert res.status_code == 302, res.text
    location = urlparse(res.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == settings.APP_BASE_URL
    assert location.path == "/login"
    return parse_qs(location.query)["error"][0]


def test_google_callback_rejects_bad_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start_google(client, monkeypatch)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": "forged"}, follow_redirects=False
    )
    assert _error_code(res) == "oauth_state"
    # no cookie at all
    client.cookies.clear()
    res = client.get(f"{BASE}/google/callback", params={"code": "abc"}, follow_redirects=False)
    assert _error_code(res) == "oauth_state"


def test_google_callback_rejects_state_from_other_browser(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_google(client, monkeypatch)
    client.cookies.set(oauth.STATE_COOKIE, "different-nonce")
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert _error_code(res) == "oauth_state"


def test_google_callback_provider_errors_redirect(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _start_google(client, monkeypatch)
    res = client.get(
        f"{BASE}/google/callback", params={"error": "access_denied"}, follow_redirects=False
    )
    assert _error_code(res) == "oauth_cancelled"

    async def failing(code: str, redirect_uri: str) -> dict[str, Any]:
        raise oauth.OAuthError("boom")

    monkeypatch.setattr(oauth, "fetch_google_profile", failing)
    client.cookies.clear()
    state = _start_google(client, monkeypatch)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert _error_code(res) == "oauth_failed"


def test_google_callback_inactive_account_redirects(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(client)
    user = db_session.execute(select(User)).scalar_one()
    user.is_active = False
    db_session.commit()
    state = _start_google(client, monkeypatch)

    async def fake_profile(code: str, redirect_uri: str) -> dict[str, Any]:
        return {"email": "alice@example.com", "email_verified": True}

    monkeypatch.setattr(oauth, "fetch_google_profile", fake_profile)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert _error_code(res) == "account_disabled"


def test_google_redirect_uri_uses_config_and_cookie_secure_in_prod(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "API_BASE_URL", "https://api.example.com")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(oauth, "is_configured", lambda: True)
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_SECRET", "secret")
    res = client.get(f"{BASE}/google", headers={"host": "evil.test"}, follow_redirects=False)
    query = parse_qs(urlparse(res.headers["location"]).query)
    assert query["redirect_uri"] == ["https://api.example.com/api/v1/auth/google/callback"]
    assert "secure" in res.headers["set-cookie"].lower()


def test_google_cookie_not_secure_in_dev(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    _start_google(client, monkeypatch)
    res = client.get(f"{BASE}/google", follow_redirects=False)
    assert "secure" not in res.headers["set-cookie"].lower()


def test_google_signin_neutralises_unverified_password_account(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    attacker = _register(client)  # attacker pre-registers the victim's email
    state = _start_google(client, monkeypatch)

    async def fake_profile(code: str, redirect_uri: str) -> dict[str, Any]:
        return {"email": "alice@example.com", "email_verified": True, "name": "Alice"}

    monkeypatch.setattr(oauth, "fetch_google_profile", fake_profile)
    res = client.get(
        f"{BASE}/google/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )
    assert res.status_code == 302
    login = client.post(
        f"{BASE}/login", json={"email": "alice@example.com", "password": CREDS["password"]}
    )
    assert login.status_code == 401
    refresh = client.post(f"{BASE}/refresh", json={"refresh_token": attacker["refresh_token"]})
    assert refresh.status_code == 401
    user = db_session.execute(select(User)).scalar_one()
    assert user.is_verified and user.hashed_password is None


def test_refresh_reuse_within_grace_does_not_revoke_sessions(client: TestClient) -> None:
    tokens = _register(client)
    first = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    again = client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401
    # The freshly rotated token still works: sessions were not wiped.
    third = client.post(f"{BASE}/refresh", json={"refresh_token": first.json()["refresh_token"]})
    assert third.status_code == 200


def test_concurrent_refresh_only_one_wins(tmp_path: Any) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as seed:
        user = User(email="race@example.com", hashed_password=None)
        seed.add(user)
        seed.commit()
        token = auth_service.issue_tokens(seed, user).refresh_token

    barrier = threading.Barrier(2)
    outcomes: list[int] = []

    def worker() -> None:
        with factory() as session:
            barrier.wait()
            try:
                auth_service.refresh_session(session, token)
                outcomes.append(200)
            except auth_service.UnauthorizedError:
                outcomes.append(401)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == [200, 401]
    with factory() as check:
        live = (
            check.execute(select(RefreshToken).where(RefreshToken.revoked.is_(False)))
            .scalars()
            .all()
        )
        assert len(live) == 1  # the winner's new token survives the loser
    engine.dispose()


def test_validation_and_rate_limit_error_shapes(client: TestClient) -> None:
    res = client.post(f"{BASE}/register", json={"email": "nope", "password": "short"})
    assert res.status_code == 422
    body = res.json()
    assert isinstance(body["detail"], str) and body["detail"]
    assert isinstance(body["errors"], list) and body["errors"]
    creds = {"email": "a@example.com", "password": "whatever1"}
    responses = [client.post(f"{BASE}/login", json=creds) for _ in range(7)]
    limited = next(r for r in responses if r.status_code == 429)
    assert limited.json()["detail"].startswith("Too many requests, try again in ")
    assert int(limited.headers["Retry-After"]) >= 1


def test_jwt_algorithm_is_pinned() -> None:
    import jwt as pyjwt

    forged = pyjwt.encode({"sub": "1", "type": "access"}, "", algorithm="none")
    assert decode_token(forged, "access") is None


def test_google_not_configured(client: TestClient) -> None:
    res = client.get(f"{BASE}/google", follow_redirects=False)
    assert res.status_code == 400
