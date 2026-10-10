"""GitHub client tests: strict URL validation and mocked API calls (no network)."""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.exceptions import NotFoundError
from app.services import github_client
from app.services.github_client import GitHubFetchError, fetch_repo_snapshot, parse_repo_url

SHA = "a" * 40
API = "https://api.github.com/repos/octo/hello"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/octo/hello", ("octo", "hello")),
        ("https://github.com/octo/hello/", ("octo", "hello")),
        ("https://github.com/octo/hello.git", ("octo", "hello")),
        ("https://github.com/octo/my.repo-name_1", ("octo", "my.repo-name_1")),
        ("  https://github.com/octo/hello  ", ("octo", "hello")),
    ],
)
def test_parse_valid(url: str, expected: tuple[str, str]) -> None:
    assert parse_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/github.com/a/b",
        "https://github.com.evil.com/a/b",
        "https://evilgithub.com/a/b",
        "http://github.com/a/b",
        "ftp://github.com/a/b",
        "https://user:pass@github.com/a/b",
        "https://user@github.com/a/b",
        "https://github.com:8443/a/b",
        "https://github.com:443/a/b",
        "https://github.com/a",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b/issues",
        "https://github.com/a/b?x=1",
        "https://github.com/a/b#frag",
        "https://github.com/a/../b",
        "https://github.com/a/..",
        "https://github.com//b",
        "https://github.com/-a/b",
        "https://github.com/a/b c",
        "https://github.com/a/b\nx",
        "https://github.com/a/b%2Fc",
        "//github.com/a/b",
        "github.com/a/b",
        "https://api.github.com/repos/a/b",
        "https://127.0.0.1/a/b",
        "",
        "x" * 400,
    ],
)
def test_parse_rejects(url: str) -> None:
    with pytest.raises(GitHubFetchError):
        parse_repo_url(url)


def _mock_repo(router: respx.MockRouter, tree: list[dict]) -> None:
    router.get(API).respond(json={"default_branch": "main", "private": False})
    router.get(f"{API}/commits/main").respond(json={"sha": SHA})
    router.get(f"{API}/git/trees/{SHA}", params={"recursive": "1"}).respond(
        json={"tree": tree, "truncated": False}
    )
    router.get(f"{API}/readme").respond(text="# Hello")


@respx.mock
async def test_fetch_snapshot_filters_files() -> None:
    tree = [
        {"path": "main.py", "type": "blob", "size": 20},
        {"path": "src/app.py", "type": "blob", "size": 20},
        {"path": "node_modules/x/index.js", "type": "blob", "size": 20},
        {"path": "dist/bundle.js", "type": "blob", "size": 20},
        {"path": "package-lock.json", "type": "blob", "size": 20},
        {"path": "logo.png", "type": "blob", "size": 20},
        {"path": "big.py", "type": "blob", "size": 10_000_000},
        {"path": "src", "type": "tree"},
    ]
    _mock_repo(respx.mock, tree)
    respx.get(f"{API}/contents/main.py").respond(text="print('hi')")
    respx.get(f"{API}/contents/src/app.py").respond(text="x = 1")

    snap = await fetch_repo_snapshot("https://github.com/octo/hello")

    assert snap.commit_sha == SHA
    assert snap.readme == "# Hello"
    assert [f.path for f in snap.files] == ["main.py", "src/app.py"]
    assert "node_modules/x/index.js" not in snap.file_tree
    assert "package-lock.json" not in snap.file_tree
    # Only api.github.com was contacted
    assert all(c.request.url.host == "api.github.com" for c in respx.calls)


@respx.mock
async def test_fetch_snapshot_respects_byte_and_file_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github_client.settings, "MAX_FILES", 2)
    monkeypatch.setattr(github_client.settings, "MAX_BYTES", 10_000)
    tree = [{"path": f"f{i}.py", "type": "blob", "size": 100} for i in range(5)]
    _mock_repo(respx.mock, tree)
    for i in range(5):
        respx.get(f"{API}/contents/f{i}.py").respond(text="y" * 100)

    snap = await fetch_repo_snapshot("https://github.com/octo/hello")

    assert len(snap.files) == 2
    assert snap.truncated is True


@respx.mock
async def test_missing_or_private_repo_is_friendly() -> None:
    respx.get(API).respond(404, json={"message": "Not Found"})
    with pytest.raises(NotFoundError, match="private"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_private_flag_rejected() -> None:
    respx.get(API).respond(json={"default_branch": "main", "private": True})
    with pytest.raises(NotFoundError):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_rate_limit_message() -> None:
    respx.get(API).respond(403, headers={"x-ratelimit-remaining": "0"}, json={})
    with pytest.raises(GitHubFetchError, match="rate limit"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_network_error_is_wrapped() -> None:
    respx.get(API).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GitHubFetchError, match="Could not reach GitHub"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


async def test_invalid_url_makes_no_request() -> None:
    with respx.mock(assert_all_called=False) as router:
        with pytest.raises(GitHubFetchError):
            await fetch_repo_snapshot("https://evil.com/github.com/a/b")
        assert router.calls.call_count == 0


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr(github_client.asyncio, "sleep", sleep)
    return sleep


@respx.mock
async def test_403_with_rate_limit_body_is_rate_limit_not_private() -> None:
    respx.get(API).respond(403, json={"message": "API rate limit exceeded for 1.2.3.4"})
    with pytest.raises(GitHubFetchError, match="rate limit"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_plain_403_is_private(no_sleep: AsyncMock) -> None:
    respx.get(API).respond(403, json={"message": "Repository access blocked"})
    with pytest.raises(NotFoundError):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_non_json_error_body_is_handled(no_sleep: AsyncMock) -> None:
    respx.get(API).respond(403, text="<html>forbidden</html>")
    with pytest.raises(NotFoundError):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_secondary_limit_retries_once_honouring_retry_after(no_sleep: AsyncMock) -> None:
    route = respx.get(API)
    route.side_effect = [
        httpx.Response(403, headers={"retry-after": "3"}, json={"message": "secondary"}),
        httpx.Response(200, json={"default_branch": "main", "private": False}),
    ]
    respx.get(f"{API}/commits/main").respond(409, json={"message": "Git Repository is empty."})

    with pytest.raises(GitHubFetchError, match="empty"):
        await fetch_repo_snapshot("https://github.com/octo/hello")

    no_sleep.assert_awaited_once_with(3.0)
    assert route.call_count == 2


@respx.mock
async def test_long_retry_after_is_not_waited_and_reports_rate_limit(no_sleep: AsyncMock) -> None:
    respx.get(API).respond(429, headers={"retry-after": "600"}, json={})
    with pytest.raises(GitHubFetchError, match="rate limit"):
        await fetch_repo_snapshot("https://github.com/octo/hello")
    no_sleep.assert_not_awaited()


@respx.mock
async def test_5xx_retried_once_then_error(no_sleep: AsyncMock) -> None:
    route = respx.get(API).respond(502)
    with pytest.raises(GitHubFetchError, match="unexpected error"):
        await fetch_repo_snapshot("https://github.com/octo/hello")
    assert route.call_count == 2


@respx.mock
async def test_moved_repo_followed_on_api_host_only() -> None:
    respx.get(API).respond(301, headers={"location": "https://api.github.com/repositories/42"})
    new = "https://api.github.com/repositories/42"
    respx.get(new).respond(json={"id": 42, "default_branch": "main", "private": False})
    respx.get(f"{new}/commits/main").respond(json={"sha": SHA})
    respx.get(f"{new}/git/trees/{SHA}", params={"recursive": "1"}).respond(
        json={"tree": [{"path": "a.py", "type": "blob", "size": 5}]}
    )
    respx.get(f"{new}/readme").respond(404)
    respx.get(f"{new}/contents/a.py").respond(text="x=1")

    snap = await fetch_repo_snapshot("https://github.com/octo/hello")

    assert [f.path for f in snap.files] == ["a.py"]
    assert all(c.request.url.host == "api.github.com" for c in respx.calls)


@respx.mock
async def test_moved_to_foreign_host_is_refused() -> None:
    respx.get(API).respond(301, headers={"location": "https://evil.example.com/x"})
    with pytest.raises(GitHubFetchError, match="moved"):
        await fetch_repo_snapshot("https://github.com/octo/hello")
    assert all(c.request.url.host == "api.github.com" for c in respx.calls)


@respx.mock
async def test_empty_repo_409() -> None:
    respx.get(API).respond(json={"default_branch": "main", "private": False})
    respx.get(f"{API}/commits/main").respond(409, json={"message": "Git Repository is empty."})
    with pytest.raises(GitHubFetchError, match="empty"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_empty_tree() -> None:
    _mock_repo(respx.mock, [])
    with pytest.raises(GitHubFetchError, match="empty"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_no_analysable_files_errors_before_openai() -> None:
    tree = [{"path": "logo.png", "type": "blob", "size": 20}]
    _mock_repo(respx.mock, tree)
    with pytest.raises(GitHubFetchError, match="No analysable source files"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_symlinks_and_submodules_skipped() -> None:
    tree = [
        {"path": "link.py", "type": "blob", "mode": "120000", "size": 10},
        {"path": "sub", "type": "commit", "mode": "160000"},
        {"path": "real.py", "type": "blob", "mode": "100644", "size": 10},
    ]
    _mock_repo(respx.mock, tree)
    respx.get(f"{API}/contents/real.py").respond(text="x = 1")

    snap = await fetch_repo_snapshot("https://github.com/octo/hello")

    assert snap.file_tree == ["real.py"]
    assert [f.path for f in snap.files] == ["real.py"]


@respx.mock
async def test_non_json_body_is_friendly() -> None:
    respx.get(API).respond(200, text="not json")
    with pytest.raises(GitHubFetchError, match="unexpected response"):
        await fetch_repo_snapshot("https://github.com/octo/hello")


@respx.mock
async def test_fork_archived_flags_and_concurrent_fetch_order() -> None:
    respx.get(API).respond(
        json={"default_branch": "main", "private": False, "fork": True, "archived": True}
    )
    respx.get(f"{API}/commits/main").respond(json={"sha": SHA})
    tree = [{"path": f"f{i}.py", "type": "blob", "size": 5} for i in range(8)]
    respx.get(f"{API}/git/trees/{SHA}", params={"recursive": "1"}).respond(json={"tree": tree})
    respx.get(f"{API}/readme").respond(404)
    for i in range(8):
        respx.get(f"{API}/contents/f{i}.py").respond(text=f"v{i} = 1")

    snap = await fetch_repo_snapshot("https://github.com/octo/hello")

    assert snap.fork is True and snap.archived is True
    assert [f.path for f in snap.files] == [f"f{i}.py" for i in range(8)]


def test_readme_cap_is_tighter_for_non_ascii() -> None:
    ascii_text = "a" * 30_000
    tamil = "தமிழ்" * 5_000
    assert len(github_client._cap_readme(ascii_text)) == github_client.MAX_README_CHARS
    assert len(github_client._cap_readme(tamil)) == github_client.MAX_README_CHARS_NON_ASCII
    assert github_client._cap_readme("") == ""
