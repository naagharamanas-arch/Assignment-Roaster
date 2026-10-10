"""Coverage for database helpers, moderation, OAuth error branches and job refund paths."""

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session, sessionmaker

import app.database as database
from app.auth import oauth
from app.auth.jwt import create_state_token
from app.models import (
    Analysis,
    Roast,
    Submission,
    SubmissionStatus,
    UsageCounter,
    User,
)
from app.services import jobs, moderation, usage_service

# ---------------------------------------------------------------- database


def test_resolve_database_url_prefers_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.DATABASE_URL", "sqlite:///from-settings")
    assert database._resolve_database_url() == "sqlite:///from-settings"


def test_resolve_database_url_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.DATABASE_URL", "")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env")
    assert database._resolve_database_url() == "sqlite:///from-env"
    monkeypatch.delenv("DATABASE_URL")
    assert database._resolve_database_url() == database._DEFAULT_URL


def test_resolve_database_url_survives_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env-only")
    monkeypatch.setitem(sys.modules, "app.config", None)  # makes `from app.config import` fail
    assert database._resolve_database_url() == "sqlite:///env-only"


def test_get_db_yields_session_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    gen = database.get_db()
    assert next(gen) is session
    session.close.assert_not_called()
    with pytest.raises(StopIteration):
        next(gen)
    session.close.assert_called_once()


def test_get_db_closes_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    gen = database.get_db()
    next(gen)
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    session.close.assert_called_once()


# -------------------------------------------------------------- moderation


def _moderation_client(flags: list[bool]) -> MagicMock:
    client = MagicMock()
    client.moderations.create = AsyncMock(
        return_value=SimpleNamespace(results=[SimpleNamespace(flagged=f) for f in flags])
    )
    return client


async def test_moderation_blank_text_skips_api(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _moderation_client([True])
    monkeypatch.setattr(moderation, "get_client", lambda: client)
    assert await moderation.is_safe("   \n") is True
    client.moderations.create.assert_not_called()


async def test_moderation_flagged_and_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    flagged = _moderation_client([False, True])
    monkeypatch.setattr(moderation, "get_client", lambda: flagged)
    assert await moderation.is_safe("bad text") is False
    flagged.moderations.create.assert_awaited_once_with(
        model=moderation.MODERATION_MODEL, input="bad text"
    )

    clean = _moderation_client([False])
    monkeypatch.setattr(moderation, "get_client", lambda: clean)
    assert await moderation.is_safe("fine") is True


def test_moderation_get_client_uses_settings_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.moderation.settings.OPENAI_API_KEY", "sk-test-not-real")
    assert moderation.get_client().api_key == "sk-test-not-real"


# ------------------------------------------------------------------- oauth


class _FakeOAuthClient:
    def __init__(self, profile: dict[str, Any] | None = None, fail: str | None = None) -> None:
        self.profile = profile or {}
        self.fail = fail

    async def __aenter__(self) -> "_FakeOAuthClient":
        return self

    async def __aexit__(self, *_a: object) -> None:
        return None

    async def fetch_token(self, *_a: Any, **_k: Any) -> dict[str, str]:
        if self.fail == "token":
            raise RuntimeError("token endpoint down")
        return {"access_token": "t"}

    async def get(self, *_a: Any, **_k: Any) -> Any:
        if self.fail == "userinfo":
            raise RuntimeError("userinfo down")
        resp = MagicMock()
        resp.json.return_value = self.profile
        if self.fail == "status":
            resp.raise_for_status.side_effect = RuntimeError("401")
        return resp


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeOAuthClient) -> None:
    monkeypatch.setattr(oauth, "_client", lambda _redirect: fake)


async def test_fetch_google_profile_success(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {"email": "a@b.com", "email_verified": True, "name": "A"}
    _patch_client(monkeypatch, _FakeOAuthClient(profile))
    assert await oauth.fetch_google_profile("code", "http://x/cb") == profile


@pytest.mark.parametrize("fail", ["token", "userinfo", "status"])
async def test_fetch_google_profile_wraps_errors(
    monkeypatch: pytest.MonkeyPatch, fail: str
) -> None:
    _patch_client(monkeypatch, _FakeOAuthClient(fail=fail))
    with pytest.raises(oauth.OAuthError, match="token exchange failed"):
        await oauth.fetch_google_profile("code", "http://x/cb")


@pytest.mark.parametrize(
    "profile",
    [
        {"email": "a@b.com", "email_verified": False},
        {"email": "a@b.com"},
        {"email_verified": True},
        {},
    ],
)
async def test_fetch_google_profile_requires_verified_email(
    monkeypatch: pytest.MonkeyPatch, profile: dict[str, Any]
) -> None:
    _patch_client(monkeypatch, _FakeOAuthClient(profile))
    with pytest.raises(oauth.OAuthError, match="not verified"):
        await oauth.fetch_google_profile("code", "http://x/cb")


def test_verify_state_branches() -> None:
    state = create_state_token("nonce-1")
    assert oauth.verify_state(state, "nonce-1") is True
    assert oauth.verify_state(state, "other") is False
    assert oauth.verify_state(state, None) is False
    assert oauth.verify_state(None, "nonce-1") is False
    assert oauth.verify_state("not-a-jwt", "nonce-1") is False


def test_is_configured_and_build_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_SECRET", "")
    assert oauth.is_configured() is False
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(oauth.settings, "GOOGLE_CLIENT_SECRET", "sec")
    assert oauth.is_configured() is True
    url, nonce = oauth.build_authorization("http://localhost/cb")
    assert url.startswith(oauth.AUTHORIZE_URL)
    assert "client_id=cid" in url and "state=" in url
    assert nonce and nonce not in url  # nonce lives only in the cookie, not the URL


# -------------------------------------------------------------------- jobs


def _user_and_sub(db: Session, status: SubmissionStatus) -> Submission:
    user = User(email="j@example.com", is_active=True)
    db.add(user)
    db.commit()
    sub = Submission(
        user_id=user.id,
        repo_url="https://github.com/octo/hello",
        owner="octo",
        repo="hello",
        status=status,
    )
    db.add(sub)
    db.commit()
    return sub


@pytest.fixture
def jobs_db(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    return db_session


async def test_pipeline_noop_when_submission_missing(jobs_db: Session) -> None:
    await jobs.run_submission_pipeline(999)  # must not raise
    assert jobs_db.query(Submission).count() == 0


async def test_regeneration_noop_when_submission_missing(jobs_db: Session) -> None:
    await jobs.run_roast_regeneration(999)
    assert jobs_db.query(Roast).count() == 0


async def test_regeneration_without_analysis_restores_done_and_refunds(jobs_db: Session) -> None:
    sub = _user_and_sub(jobs_db, SubmissionStatus.roasting)
    sub.usage_date = usage_service.consume_roast(jobs_db, sub.user_id)
    jobs_db.commit()
    assert usage_service.roasts_used_today(jobs_db, sub.user_id) == 1

    await jobs.run_roast_regeneration(sub.id)

    jobs_db.expire_all()
    refreshed = jobs_db.get(Submission, sub.id)
    assert refreshed is not None
    assert refreshed.status == SubmissionStatus.done  # restored, not failed
    assert refreshed.error == jobs.GENERIC_ERROR  # visible, old roast kept
    assert usage_service.roasts_used_today(jobs_db, sub.user_id) == 0
    assert jobs_db.query(Roast).count() == 0


async def test_regeneration_writer_crash_refunds_and_hides_detail(
    jobs_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = _user_and_sub(jobs_db, SubmissionStatus.roasting)
    jobs_db.add(
        Analysis(
            submission_id=sub.id,
            model="m",
            score=50,
            categories={
                "structure": 1,
                "readme": 1,
                "code_quality": 1,
                "tests": 1,
                "git_hygiene": 1,
                "security": 1,
                "originality": 1,
            },
            strengths=[],
            issues=[],
        )
    )
    sub.usage_date = usage_service.consume_roast(jobs_db, sub.user_id)
    jobs_db.commit()

    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("secret sk-leak")

    import app.services.roast_writer as writer

    monkeypatch.setattr(writer, "write_roast", boom)
    await jobs.run_roast_regeneration(sub.id)

    jobs_db.expire_all()
    refreshed = jobs_db.get(Submission, sub.id)
    assert refreshed is not None
    assert refreshed.status == SubmissionStatus.done
    assert refreshed.error == jobs.GENERIC_ERROR  # visible; detail hidden
    counter = jobs_db.query(UsageCounter).one()
    assert counter.roasts_used == 0


def test_fail_ignores_missing_submission(jobs_db: Session) -> None:
    jobs._fail(jobs_db, 12345, "x")  # no exception, nothing created
    assert jobs_db.query(UsageCounter).count() == 0


def test_fail_marks_failed_with_message_and_never_goes_negative(jobs_db: Session) -> None:
    sub = _user_and_sub(jobs_db, SubmissionStatus.analysing)
    jobs._fail(jobs_db, sub.id, "nice message")  # no counter exists -> refund is a no-op
    jobs_db.expire_all()
    refreshed = jobs_db.get(Submission, sub.id)
    assert refreshed is not None
    assert refreshed.status == SubmissionStatus.failed
    assert refreshed.error == "nice message"
    assert jobs_db.query(UsageCounter).count() == 0


# ------------------------------------------------- google callback branches


def _callback(client: Any, monkeypatch: pytest.MonkeyPatch, impl: Any) -> Any:
    monkeypatch.setattr(oauth, "fetch_google_profile", impl)
    client.cookies.set(oauth.STATE_COOKIE, "n1")
    return client.get(
        "/api/v1/auth/google/callback",
        params={"code": "c", "state": create_state_token("n1")},
        follow_redirects=False,
    )


def test_google_callback_provider_failure_redirects(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fail(*_a: Any, **_k: Any) -> None:
        raise oauth.OAuthError("Google token exchange failed")

    resp = _callback(client, monkeypatch, fail)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/login?error=oauth_failed")


def test_google_callback_disabled_account_rejected(
    client: Any, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    db_session.add(User(email="off@example.com", is_active=False))
    db_session.commit()

    async def ok(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"email": "off@example.com", "email_verified": True, "name": "Off"}

    resp = _callback(client, monkeypatch, ok)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/login?error=account_disabled")
    assert "access_token" not in resp.headers.get("location", "")
