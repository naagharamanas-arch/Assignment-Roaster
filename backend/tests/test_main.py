"""Smoke and end-to-end tests of the REAL app from app.main (GitHub/OpenAI mocked)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import get_db
from app.main import app as real_app
from app.routers import auth as auth_router
from app.schemas.pipeline import (
    AnalysisResult,
    CategoryScores,
    Issue,
    RepoSnapshotData,
    RoastResult,
    SnapshotFile,
)
from app.services import github_client, jobs

PASSWORD = "password123"


@pytest.fixture(autouse=True)
def _reset_limiter() -> Iterator[None]:
    """Rate-limit state is process-global; clear it before and after each test."""
    auth_router.limiter.reset()
    real_app.state.limiter.reset()
    yield
    auth_router.limiter.reset()
    real_app.state.limiter.reset()


@pytest.fixture
def main_client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Real app with get_db -> in-memory SQLite and all external calls mocked."""

    def _db() -> Iterator[Session]:
        yield db_session

    async def fake_fetch(url: str) -> RepoSnapshotData:
        return RepoSnapshotData(
            owner="octo",
            repo="hello",
            commit_sha="a" * 40,
            file_tree=["a.py"],
            readme="hi",
            files=[SnapshotFile(path="a.py", content="x=1")],
            total_bytes=3,
        )

    async def fake_analyze(snapshot: RepoSnapshotData, brief: str | None) -> AnalysisResult:
        return AnalysisResult(
            score=61,
            categories=CategoryScores(
                structure=50,
                readme=40,
                code_quality=60,
                tests=0,
                git_hygiene=70,
                security=80,
                originality=50,
            ),
            strengths=["ok"],
            issues=[Issue(file="a.py", problem="no tests", severity="high")],
            model="fake",
        )

    async def fake_write(analysis: AnalysisResult, level: str, style: str) -> RoastResult:
        return RoastResult(
            title="Roasted", roast_text="roast body", one_liner="one", fixes=["add tests"]
        )

    import app.services.openai_analyzer as analyzer
    import app.services.roast_writer as writer

    monkeypatch.setattr(github_client, "fetch_repo_snapshot", fake_fetch)
    monkeypatch.setattr(analyzer, "analyze_repo", fake_analyze)
    monkeypatch.setattr(writer, "write_roast", fake_write)
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    real_app.dependency_overrides[get_db] = _db
    try:
        with TestClient(real_app) as client:
            yield client
    finally:
        real_app.dependency_overrides.clear()


def _register(client: TestClient, email: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_health(main_client: TestClient) -> None:
    resp = main_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_v1_routes_mounted() -> None:
    paths = set(real_app.openapi()["paths"])
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/submissions",
        "/api/v1/submissions/{submission_id}",
        "/api/v1/roasts/{share_slug}",
        "/api/v1/roasts/{roast_id}/visibility",
        "/health",
    }
    assert expected <= paths
    assert all(p == "/health" or p.startswith("/api/v1/") for p in paths)


def test_cors_allows_app_base_url(main_client: TestClient) -> None:
    origin = settings.APP_BASE_URL
    resp = main_client.get("/health", headers={"Origin": origin})
    assert resp.headers["access-control-allow-origin"] == origin
    assert resp.headers["access-control-allow-credentials"] == "true"

    preflight = main_client.options(
        "/api/v1/submissions",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


def test_cors_rejects_other_origin(main_client: TestClient) -> None:
    resp = main_client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/submissions"),
        ("POST", "/api/v1/submissions"),
        ("GET", "/api/v1/submissions/1"),
        ("DELETE", "/api/v1/submissions/1"),
        ("PUT", "/api/v1/roasts/1/visibility"),
    ],
)
def test_protected_endpoints_require_token(main_client: TestClient, method: str, path: str) -> None:
    resp = main_client.request(method, path, json={"repo_url": "x", "is_public": True})
    assert resp.status_code == 401


def test_invalid_token_is_401(main_client: TestClient) -> None:
    resp = main_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_end_to_end_flow(main_client: TestClient) -> None:
    alice = _register(main_client, "alice@example.com")

    login = main_client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert main_client.get("/api/v1/auth/me", headers=headers).json()["email"] == (
        "alice@example.com"
    )

    created = main_client.post(
        "/api/v1/submissions",
        json={"repo_url": "https://github.com/octo/hello", "roast_level": "medium"},
        headers=headers,
    )
    assert created.status_code == 201
    sub_id = created.json()["id"]

    detail = main_client.get(f"/api/v1/submissions/{sub_id}", headers=headers).json()
    assert detail["status"] == "done"
    assert detail["analysis"]["score"] == 61
    assert detail["roast"]["title"] == "Roasted"
    assert detail["roast"]["is_public"] is False
    roast_id, slug = detail["roast"]["id"], detail["roast"]["share_slug"]

    # private until the owner publishes it
    assert main_client.get(f"/api/v1/roasts/{slug}").status_code == 404
    toggled = main_client.put(
        f"/api/v1/roasts/{roast_id}/visibility", json={"is_public": True}, headers=headers
    )
    assert toggled.status_code == 200

    public = main_client.get(f"/api/v1/roasts/{slug}")  # no auth header
    assert public.status_code == 200
    assert public.json()["roast_text"] == "roast body"
    assert public.json()["score"] == 61
    assert "alice@example.com" not in public.text

    # a second user cannot see or modify Alice's submission
    bob = _register(main_client, "bob@example.com")
    assert alice != bob
    assert main_client.get(f"/api/v1/submissions/{sub_id}", headers=bob).status_code == 404
    assert main_client.delete(f"/api/v1/submissions/{sub_id}", headers=bob).status_code == 404
    assert (
        main_client.put(
            f"/api/v1/roasts/{roast_id}/visibility", json={"is_public": False}, headers=bob
        ).status_code
        == 404
    )
    assert main_client.get("/api/v1/submissions", headers=bob).json() == []
    # still public: bob's failed attempt changed nothing
    assert main_client.get(f"/api/v1/roasts/{slug}").status_code == 200


def test_login_rate_limited_after_five_attempts(main_client: TestClient) -> None:
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    statuses = [main_client.post("/api/v1/auth/login", json=body).status_code for _ in range(6)]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_rate_limit_state_does_not_leak_between_tests(main_client: TestClient) -> None:
    """The previous test exhausted the login limit; the autouse reset must clear it."""
    body = {"email": "nobody@example.com", "password": "wrong-password"}
    assert main_client.post("/api/v1/auth/login", json=body).status_code == 401
