"""Atomic quota, global cap, stale-job reaper, refund and share-privacy tests."""
# ruff: noqa: F811

import datetime as dt
import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.exceptions import RateLimitError
from app.models import Base, Roast, Submission, SubmissionStatus, UsageCounter, User
from app.services import jobs, usage_service
from tests.test_submissions import REPO, _make_user, _submit, api, calls, current, user  # noqa: F401  # noqa: F401


def test_concurrent_consume_is_exact(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'c.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory() as s:
        u = User(email="x@example.com", is_active=True)
        s.add(u)
        s.commit()
        uid = u.id
    results: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(12)

    def worker() -> None:
        with factory() as s:
            barrier.wait()
            try:
                usage_service.consume_roast(s, uid)
                s.commit()
                outcome = "ok"
            except RateLimitError:
                s.rollback()
                outcome = "limited"
            with lock:
                results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == settings.DAILY_ROAST_LIMIT
    assert results.count("limited") == 12 - settings.DAILY_ROAST_LIMIT
    with factory() as s:
        assert usage_service.roasts_used_today(s, uid) == settings.DAILY_ROAST_LIMIT
    engine.dispose()


def test_refund_never_goes_negative_and_targets_date(db_session: Session, user: User) -> None:
    day = usage_service.consume_roast(db_session, user.id)
    db_session.commit()
    yesterday = day - dt.timedelta(days=1)
    usage_service.refund_roast(db_session, user.id, yesterday)  # no such counter: no-op
    usage_service.refund_roast(db_session, user.id, day)
    usage_service.refund_roast(db_session, user.id, day)
    db_session.commit()
    assert usage_service.roasts_used_today(db_session, user.id) == 0


def test_global_cap_returns_503(
    api: Any, db_session: Session, monkeypatch: pytest.MonkeyPatch, user: User
) -> None:
    monkeypatch.setattr(settings, "GLOBAL_DAILY_JOB_CAP", 1)
    assert _submit(api).status_code == 201
    db_session.expire_all()
    resp = _submit(api, "https://github.com/octo/other")
    assert resp.status_code == 503
    assert "tomorrow" in resp.json()["detail"]
    sub_id = api.get("/api/v1/submissions").json()[0]["id"]
    assert api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate").status_code == 503


def test_regenerate_makes_old_share_slug_private(api: Any, db_session: Session) -> None:
    sub_id = _submit(api).json()["id"]
    db_session.expire_all()
    old = api.get(f"/api/v1/submissions/{sub_id}").json()["roast"]
    api.put(f"/api/v1/roasts/{old['id']}/visibility", json={"is_public": True})
    assert api.get(f"/api/v1/roasts/{old['share_slug']}").status_code == 200
    assert api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate").status_code == 202
    db_session.expire_all()
    new = api.get(f"/api/v1/submissions/{sub_id}").json()["roast"]
    assert new["id"] != old["id"] and new["is_public"] is False
    assert api.get(f"/api/v1/roasts/{old['share_slug']}").status_code == 404
    assert api.get(f"/api/v1/roasts/{new['share_slug']}").status_code == 404


def test_list_has_score_limit_offset(api: Any, db_session: Session) -> None:
    for name in ("one", "two", "three"):
        assert _submit(api, f"https://github.com/octo/{name}").status_code == 201
        db_session.expire_all()
    rows = api.get("/api/v1/submissions").json()
    assert len(rows) == 3 and all(r["score"] == 55 for r in rows)
    page = api.get("/api/v1/submissions?limit=1&offset=1").json()
    assert len(page) == 1 and page[0]["id"] == rows[1]["id"]
    assert api.get("/api/v1/submissions?limit=101").status_code == 422
    assert api.get("/api/v1/submissions?offset=-1").status_code == 422


def _stuck(db: Session, user: User, status: SubmissionStatus, age_min: int) -> Submission:
    day = usage_service.consume_roast(db, user.id)
    sub = Submission(
        user_id=user.id,
        repo_url=REPO,
        owner="octo",
        repo="hello",
        status=status,
        usage_date=day,
        updated_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=age_min),
        created_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=age_min),
    )
    db.add(sub)
    db.commit()
    return sub


def test_reaper_fails_stale_and_refunds_once(db_session: Session, user: User) -> None:
    stale = _stuck(db_session, user, SubmissionStatus.analysing, settings.STALE_JOB_MINUTES + 5)
    fresh = _stuck(db_session, user, SubmissionStatus.fetching, 0)
    assert jobs.reap_stale_submissions(db_session) == 1
    assert jobs.reap_stale_submissions(db_session) == 0  # exactly once
    db_session.expire_all()
    assert db_session.get(Submission, stale.id).status == SubmissionStatus.failed  # type: ignore[union-attr]
    assert db_session.get(Submission, stale.id).error  # type: ignore[union-attr]
    assert db_session.get(Submission, fresh.id).status == SubmissionStatus.fetching  # type: ignore[union-attr]
    assert usage_service.roasts_used_today(db_session, user.id) == 1


def test_reaper_restores_stale_regeneration(db_session: Session, user: User) -> None:
    sub = _stuck(db_session, user, SubmissionStatus.roasting, settings.STALE_JOB_MINUTES + 5)
    db_session.add(
        Roast(
            submission_id=sub.id,
            title="old",
            roast_text="t",
            fixes=[],
            model="m",
            share_slug="slug-old-1",
        )
    )
    db_session.commit()
    assert jobs.reap_stale_submissions(db_session) == 1
    db_session.expire_all()
    got = db_session.get(Submission, sub.id)
    assert got is not None and got.status == SubmissionStatus.done and got.error
    assert usage_service.roasts_used_today(db_session, user.id) == 0
    assert db_session.scalars(select(Roast)).all()  # old roast kept


def test_deleted_mid_pipeline_refunds_carried_counter(
    api: Any, calls: Any, db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def delete_then_fetch(url: str) -> Any:
        db_session.query(Submission).delete()
        db_session.commit()
        raise RuntimeError("gone")

    monkeypatch.setattr(jobs.github_client, "fetch_repo_snapshot", delete_then_fetch)
    assert _submit(api).status_code == 201
    db_session.expire_all()
    assert usage_service.roasts_used_today(db_session, user.id) == 0


def test_pipeline_timeout_fails_and_refunds(
    api: Any, calls: Any, db_session: Session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async def slow(url: str) -> Any:
        await asyncio.sleep(5)

    monkeypatch.setattr(jobs.github_client, "fetch_repo_snapshot", slow)
    monkeypatch.setattr(settings, "PIPELINE_TIMEOUT_SECONDS", 0.05)
    sub_id = _submit(api).json()["id"]
    db_session.expire_all()
    detail = api.get(f"/api/v1/submissions/{sub_id}").json()
    assert detail["status"] == "failed" and "timed out" in detail["error"]
    assert usage_service.roasts_used_today(db_session, user.id) == 0


def test_regen_failure_sets_visible_error_keeps_roast(
    api: Any, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    sub_id = _submit(api).json()["id"]
    db_session.expire_all()

    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(sys.modules["app.services.roast_writer"], "write_roast", boom)
    api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate")
    db_session.expire_all()
    detail = api.get(f"/api/v1/submissions/{sub_id}").json()
    assert detail["status"] == "done" and detail["error"] and detail["roast"]["title"]
    counter = db_session.scalars(select(UsageCounter)).one()
    assert counter.roasts_used == 1
