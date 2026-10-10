"""Submission, pipeline, usage-limit and public-share tests (GitHub and OpenAI mocked)."""

import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.dependencies import get_current_user
from app.exceptions import register_exception_handlers
from app.models import Analysis, Roast, Submission, SubmissionStatus, User
from app.routers import roasts as roasts_router
from app.routers import submissions as submissions_router
from app.schemas.pipeline import (
    AnalysisResult,
    CategoryScores,
    Issue,
    RepoSnapshotData,
    RoastResult,
    SnapshotFile,
)
from app.services import github_client, jobs

REPO = "https://github.com/octo/hello"


def _analysis() -> AnalysisResult:
    cats = CategoryScores(
        structure=50,
        readme=40,
        code_quality=60,
        tests=0,
        git_hygiene=70,
        security=80,
        originality=50,
    )
    return AnalysisResult(
        score=55,
        categories=cats,
        strengths=["ok"],
        issues=[Issue(file="a.py", problem="no tests", severity="high")],
        model="fake",
        prompt_tokens=1,
        completion_tokens=2,
    )


class Calls:
    """Counters for mocked services."""

    def __init__(self) -> None:
        self.analyze = 0
        self.roast = 0
        self.fetch = 0
        self.fail_fetch = False
        self.sha = "b" * 40


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> Calls:
    """Mock GitHub fetch, analyzer and roast writer; point jobs at the test DB."""
    state = Calls()

    async def fake_fetch(url: str) -> RepoSnapshotData:
        state.fetch += 1
        if state.fail_fetch:
            raise github_client.GitHubFetchError("Repository not found or it is private.")
        return RepoSnapshotData(
            owner="octo",
            repo="hello",
            commit_sha=state.sha,
            file_tree=["a.py"],
            readme="hi",
            files=[SnapshotFile(path="a.py", content="x=1")],
            total_bytes=3,
        )

    async def fake_analyze(snapshot: RepoSnapshotData, brief: str | None) -> AnalysisResult:
        state.analyze += 1
        return _analysis()

    async def fake_write(analysis: AnalysisResult, level: str, style: str) -> RoastResult:
        state.roast += 1
        return RoastResult(
            title=f"T-{level}-{style}",
            roast_text="roast",
            one_liner="one",
            fixes=["add tests"],
            model="fake",
        )

    for name in ("openai_analyzer", "roast_writer"):
        full = f"app.services.{name}"
        if full not in sys.modules:
            try:
                __import__(full)
            except ImportError:
                monkeypatch.setitem(sys.modules, full, types.ModuleType(full))
    monkeypatch.setattr(
        sys.modules["app.services.openai_analyzer"], "analyze_repo", fake_analyze, raising=False
    )
    monkeypatch.setattr(
        sys.modules["app.services.roast_writer"], "write_roast", fake_write, raising=False
    )
    monkeypatch.setattr(github_client, "fetch_repo_snapshot", fake_fetch)
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    return state


def _make_user(db: Session, email: str) -> User:
    user = User(email=email, is_active=True)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def user(db_session: Session) -> User:
    return _make_user(db_session, "me@example.com")


@pytest.fixture
def current(user: User) -> dict[str, User]:
    return {"user": user}


@pytest.fixture
def api(db_session: Session, current: dict[str, User], calls: Calls) -> Iterator[TestClient]:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(submissions_router.router, prefix="/api/v1")
    app.include_router(roasts_router.router, prefix="/api/v1")

    def _db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with TestClient(app) as client:
        yield client


def _submit(api: TestClient, url: str = REPO, **extra: Any) -> Any:
    return api.post("/api/v1/submissions", json={"repo_url": url, **extra})


def test_full_pipeline_and_detail(api: TestClient, calls: Calls, db_session: Session) -> None:
    resp = _submit(api, assignment_brief="build a todo app", roast_level="savage")
    assert resp.status_code == 201
    sub_id = resp.json()["id"]
    db_session.expire_all()

    detail = api.get(f"/api/v1/submissions/{sub_id}").json()
    assert detail["status"] == "done"
    assert detail["commit_sha"] == "b" * 40
    assert detail["analysis"]["score"] == 55
    assert detail["roast"]["title"] == "T-savage-tamil_script"
    assert detail["roast"]["is_public"] is False
    assert len(detail["roast"]["share_slug"]) >= 8
    assert api.get(f"/api/v1/submissions/{sub_id}/analysis").json()["score"] == 55
    assert len(api.get("/api/v1/submissions").json()) == 1


def test_invalid_urls_rejected(api: TestClient) -> None:
    for url in (
        "https://evil.com/github.com/a/b",
        "http://github.com/a/b",
        "https://u:p@github.com/a/b",
        "https://github.com:81/a/b",
    ):
        assert _submit(api, url).status_code == 400


def test_pipeline_failure_sets_safe_error_and_refunds(
    api: TestClient, calls: Calls, db_session: Session
) -> None:
    calls.fail_fetch = True
    sub_id = _submit(api).json()["id"]
    db_session.expire_all()
    detail = api.get(f"/api/v1/submissions/{sub_id}").json()
    assert detail["status"] == "failed"
    assert "private" in detail["error"]
    assert detail["roast"] is None
    # quota refunded and failed submission does not block a retry
    calls.fail_fetch = False
    assert _submit(api).status_code == 201


def test_unexpected_error_is_hidden(
    api: TestClient, calls: Calls, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("secret internal detail sk-123")

    monkeypatch.setattr(sys.modules["app.services.openai_analyzer"], "analyze_repo", boom)
    sub_id = _submit(api).json()["id"]
    db_session.expire_all()
    detail = api.get(f"/api/v1/submissions/{sub_id}").json()
    assert detail["status"] == "failed"
    assert "sk-123" not in detail["error"]


def test_repo_hourly_limit(api: TestClient) -> None:
    assert _submit(api).status_code == 201
    resp = _submit(api, "https://github.com/Octo/Hello.git")
    assert resp.status_code == 429
    assert "minute" in resp.json()["detail"]
    assert _submit(api, "https://github.com/octo/other").status_code == 201


def test_daily_limit_and_regenerate_counts(
    api: TestClient, calls: Calls, db_session: Session
) -> None:
    sub_id = _submit(api).json()["id"]  # 1
    r = api.post(
        f"/api/v1/submissions/{sub_id}/roast/regenerate",
        json={"roast_level": "mild", "language_style": "tanglish"},
    )  # 2
    assert r.status_code == 202
    db_session.expire_all()
    assert api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate").status_code == 202  # 3
    assert _submit(api, "https://github.com/octo/two").status_code == 429
    assert api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate").status_code == 429
    db_session.expire_all()
    assert db_session.query(Roast).filter_by(submission_id=sub_id).count() == 3
    assert calls.analyze == 1  # regenerate reuses stored analysis


def test_regenerate_requires_done(api: TestClient, db_session: Session, user: User) -> None:
    sub = Submission(
        user_id=user.id,
        repo_url=REPO,
        owner="octo",
        repo="hello",
        status=SubmissionStatus.analysing,
    )
    db_session.add(sub)
    db_session.commit()
    assert api.post(f"/api/v1/submissions/{sub.id}/roast/regenerate").status_code == 409


def test_analysis_cache_by_commit(api: TestClient, calls: Calls, db_session: Session) -> None:
    _submit(api)
    db_session.expire_all()
    other = _make_user(db_session, "b@example.com")
    api.app.dependency_overrides[get_current_user] = lambda: other  # type: ignore[attr-defined]
    _submit(api)
    assert calls.analyze == 1
    assert calls.roast == 2
    assert db_session.query(Analysis).count() == 2
    calls.sha = "c" * 40  # new commit -> fresh analysis
    third = _make_user(db_session, "c@example.com")
    api.app.dependency_overrides[get_current_user] = lambda: third  # type: ignore[attr-defined]
    _submit(api)
    assert calls.analyze == 2


def test_ownership(api: TestClient, db_session: Session, current: dict[str, User]) -> None:
    sub_id = _submit(api).json()["id"]
    db_session.expire_all()
    roast_id = api.get(f"/api/v1/submissions/{sub_id}").json()["roast"]["id"]
    current["user"] = _make_user(db_session, "evil@example.com")
    assert api.get(f"/api/v1/submissions/{sub_id}").status_code == 404
    assert api.get(f"/api/v1/submissions/{sub_id}/analysis").status_code == 404
    assert api.delete(f"/api/v1/submissions/{sub_id}").status_code == 404
    assert api.post(f"/api/v1/submissions/{sub_id}/roast/regenerate").status_code == 404
    assert (
        api.put(f"/api/v1/roasts/{roast_id}/visibility", json={"is_public": True}).status_code
        == 404
    )
    assert api.get("/api/v1/submissions").json() == []


def test_public_share_and_delete(
    api: TestClient, db_session: Session, current: dict[str, User], user: User
) -> None:
    sub_id = _submit(api, assignment_brief="private brief").json()["id"]
    db_session.expire_all()
    roast = api.get(f"/api/v1/submissions/{sub_id}").json()["roast"]
    slug = roast["share_slug"]

    assert api.get(f"/api/v1/roasts/{slug}").status_code == 404  # private by default

    on = api.put(f"/api/v1/roasts/{roast['id']}/visibility", json={"is_public": True})
    assert on.status_code == 200 and on.json()["is_public"] is True

    current["user"] = _make_user(db_session, "anon@example.com")
    api.app.dependency_overrides.pop(get_current_user)  # type: ignore[attr-defined]
    pub = api.get(f"/api/v1/roasts/{slug}")  # no auth needed
    assert pub.status_code == 200
    body = pub.json()
    assert body["score"] == 55 and body["title"].startswith("T-")
    flat = str(body)
    assert "me@example.com" not in flat and "private brief" not in flat
    assert not {"user_id", "email", "assignment_brief", "id", "share_slug", "submission_id"} & set(
        body
    )

    api.app.dependency_overrides[get_current_user] = lambda: user  # type: ignore[attr-defined]
    api.put(f"/api/v1/roasts/{roast['id']}/visibility", json={"is_public": False})
    assert api.get(f"/api/v1/roasts/{slug}").status_code == 404

    assert api.delete(f"/api/v1/submissions/{sub_id}").status_code == 204
    db_session.expire_all()
    assert db_session.query(Submission).count() == 0
    assert api.get(f"/api/v1/submissions/{sub_id}").status_code == 404
