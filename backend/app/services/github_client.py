"""Read-only GitHub client.

Only ``https://github.com/{owner}/{repo}`` URLs are accepted, and only
``https://api.github.com`` is ever contacted. Repo code is never cloned or executed.
"""

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.exceptions import AppError, NotFoundError
from app.schemas.pipeline import RepoSnapshotData, SnapshotFile

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_REPO_URL_RE = re.compile(
    r"https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]{1,100}?)"
    r"(?:\.git)?/?"
)
_SHA_RE = re.compile(r"[0-9a-f]{40}")

MAX_TREE_ENTRIES = 500
MAX_FILE_BYTES = 40_000
MAX_README_CHARS = 20_000
MAX_README_CHARS_NON_ASCII = 6_000
REQUEST_TIMEOUT = 20.0
FETCH_CONCURRENCY = 5
FETCH_TOTAL_TIMEOUT = 60.0
MAX_RETRY_WAIT = 10.0
SERVER_ERROR_RETRY_DELAY = 1.0
SYMLINK_MODE = "120000"

SKIP_DIRS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".idea",
    ".vscode",
    "target",
    "out",
    "coverage",
    "site-packages",
    "bower_components",
}
LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.sum",
    "uv.lock",
    "bun.lockb",
}
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".swift",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".vue",
    ".svelte",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".md",
    ".txt",
    ".ipynb",
}
SKIP_EXTENSIONS = {".min.js", ".min.css", ".map", ".svg", ".lock"}
CONFIG_NAMES = {"dockerfile", "requirements.txt", "package.json", "pyproject.toml", "makefile"}


class GitHubFetchError(AppError):
    """A GitHub fetch failed in a way worth showing to the user."""

    status_code = 400
    default_detail = "Could not fetch the repository from GitHub"


def parse_repo_url(url: str) -> tuple[str, str]:
    """Validate a GitHub repo URL strictly and return (owner, repo).

    Raises GitHubFetchError for anything other than https://github.com/{owner}/{repo}.
    """
    if not isinstance(url, str) or len(url) > 300:
        raise GitHubFetchError("Enter a valid GitHub repository URL")
    match = _REPO_URL_RE.fullmatch(url.strip())
    if not match:
        raise GitHubFetchError("Only public https://github.com/{owner}/{repo} URLs are supported")
    owner, repo = match.group("owner"), match.group("repo")
    if repo in {".", ".."} or owner.endswith("-"):
        raise GitHubFetchError("Enter a valid GitHub repository URL")
    return owner, repo


def _headers(raw: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "assignment-roaster",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


RATE_LIMIT_MESSAGE = "GitHub rate limit reached. Please try again in a few minutes."


def _error_message(resp: httpx.Response) -> str:
    """Best-effort lowercase 'message' from a JSON error body (empty if not JSON)."""
    try:
        data = resp.json()
    except ValueError:
        return ""
    if isinstance(data, dict):
        return str(data.get("message", "")).lower()
    return ""


def _is_rate_limited(resp: httpx.Response) -> bool:
    if resp.status_code == 429:
        return True
    if resp.status_code != 403:
        return False
    return (
        "retry-after" in resp.headers
        or resp.headers.get("x-ratelimit-remaining") == "0"
        or "rate limit" in _error_message(resp)
    )


def _check(resp: httpx.Response) -> None:
    """Translate GitHub error responses into friendly errors."""
    if resp.status_code < 400:
        return
    if _is_rate_limited(resp):
        raise GitHubFetchError(RATE_LIMIT_MESSAGE)
    if resp.status_code == 409:
        raise GitHubFetchError("This repository is empty, so there is nothing to review.")
    if resp.status_code in (404, 403, 401):
        raise NotFoundError("Repository not found or it is private. Only public repos work.")
    raise GitHubFetchError("GitHub returned an unexpected error. Please try again later.")


def _retry_delay(resp: httpx.Response) -> float | None:
    """Seconds to wait before the single retry, or None when a retry is not worthwhile."""
    if resp.status_code >= 500:
        return SERVER_ERROR_RETRY_DELAY
    if resp.status_code in (403, 429) and "retry-after" in resp.headers:
        try:
            wait = float(resp.headers["retry-after"])
        except ValueError:
            return None
        return max(wait, 0.0) if wait <= MAX_RETRY_WAIT else None
    return None


def _remaining(resp: httpx.Response) -> str | None:
    return resp.headers.get("x-ratelimit-remaining")


async def _get(client: httpx.AsyncClient, url: str, *, raw: bool = False) -> httpx.Response:
    """GET with one bounded retry for 5xx and secondary rate limits (honours retry-after)."""
    resp = await client.get(url, headers=_headers(raw))
    logger.debug("GitHub %s remaining=%s", resp.status_code, _remaining(resp))
    delay = _retry_delay(resp)
    if delay is None:
        return resp
    logger.info("GitHub returned %d; retrying once after %.1fs", resp.status_code, delay)
    await asyncio.sleep(delay)
    resp = await client.get(url, headers=_headers(raw))
    logger.debug("GitHub retry %s remaining=%s", resp.status_code, _remaining(resp))
    return resp


def _is_skipped(path: str) -> bool:
    parts = path.split("/")
    if any(p.lower() in SKIP_DIRS for p in parts[:-1]):
        return True
    name = parts[-1].lower()
    if name in LOCKFILES or name.endswith(tuple(SKIP_EXTENSIONS)):
        return True
    return False


def _is_source(path: str) -> bool:
    name = path.rsplit("/", 1)[-1].lower()
    if name in CONFIG_NAMES:
        return True
    dot = name.rfind(".")
    return dot > 0 and name[dot:] in SOURCE_EXTENSIONS


def _priority(path: str) -> tuple[int, int, str]:
    """Lower sorts first: shallow code files, then tests/config, then docs/data."""
    name = path.rsplit("/", 1)[-1].lower()
    ext = name[name.rfind(".") :] if "." in name else ""
    if ext in {".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ipynb"}:
        rank = 2
    else:
        rank = 0
    return (rank, path.count("/"), path)


def _looks_binary(text: str) -> bool:
    return "\x00" in text


def _json_dict(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        raise GitHubFetchError("GitHub returned an unexpected response.") from exc
    if not isinstance(data, dict):
        raise GitHubFetchError("GitHub returned an unexpected response.")
    return data


async def _get_json(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    resp = await _get(client, f"{GITHUB_API}{path}")
    _check(resp)
    return _json_dict(resp)


async def _get_repo_info(client: httpx.AsyncClient, base: str) -> tuple[dict[str, Any], str]:
    """Fetch repo info; follow a rename/transfer redirect only to api.github.com.

    Returns (info, base path to use for the remaining calls).
    """
    resp = await _get(client, f"{GITHUB_API}{base}")
    if resp.status_code in (301, 302, 307, 308):
        location = resp.headers.get("location", "")
        if not location.startswith(f"{GITHUB_API}/") or ".." in location:
            raise GitHubFetchError("This repository has moved and cannot be followed.")
        resp = await _get(client, location)
        _check(resp)
        info = _json_dict(resp)
        repo_id = info.get("id")
        if not isinstance(repo_id, int) or isinstance(repo_id, bool):
            raise GitHubFetchError("This repository has moved and cannot be followed.")
        return info, f"/repositories/{repo_id}"
    _check(resp)
    return _json_dict(resp), base


def _cap_readme(text: str) -> str:
    """Cap README by characters, and harder for non-ASCII text (costs more tokens)."""
    if not text:
        return text
    non_ascii = sum(1 for ch in text[:MAX_README_CHARS] if ord(ch) > 127)
    limit = (
        MAX_README_CHARS_NON_ASCII
        if non_ascii / min(len(text), MAX_README_CHARS) > 0.2
        else MAX_README_CHARS
    )
    return text[:limit]


async def fetch_repo_snapshot(repo_url: str) -> RepoSnapshotData:
    """Fetch a trimmed snapshot (tree, README, selected files) of a public repo."""
    owner, repo = parse_repo_url(repo_url)
    base = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
            info, base = await _get_repo_info(client, base)
            if info.get("private"):
                raise NotFoundError(
                    "Repository not found or it is private. Only public repos work."
                )
            branch = str(info.get("default_branch") or "main")
            commit = await _get_json(client, f"{base}/commits/{quote(branch, safe='')}")
            sha = str(commit.get("sha", ""))
            if not _SHA_RE.fullmatch(sha):
                raise GitHubFetchError("Could not resolve the latest commit of this repository.")
            tree = await _get_json(client, f"{base}/git/trees/{sha}?recursive=1")

            raw_tree = tree.get("tree")
            if not isinstance(raw_tree, list) or not raw_tree:
                raise GitHubFetchError("This repository is empty, so there is nothing to review.")
            entries = [
                e
                for e in raw_tree
                if isinstance(e, dict)
                and e.get("type") == "blob"
                and e.get("mode") != SYMLINK_MODE
                and isinstance(e.get("path"), str)
            ]
            truncated = bool(tree.get("truncated"))
            kept = [e for e in entries if not _is_skipped(e["path"])]
            file_tree = [e["path"] for e in kept][:MAX_TREE_ENTRIES]
            if len(kept) > MAX_TREE_ENTRIES:
                truncated = True

            readme = await _fetch_readme(client, base, sha)

            candidates = sorted(
                (
                    e
                    for e in kept
                    if _is_source(e["path"])
                    and not e["path"].rsplit("/", 1)[-1].lower().startswith("readme")
                    and 0 < int(e.get("size", 0)) <= MAX_FILE_BYTES
                ),
                key=lambda e: _priority(e["path"]),
            )
            selected: list[dict[str, Any]] = []
            budget = len(readme.encode()) if readme else 0
            for entry in candidates:
                if len(selected) >= settings.MAX_FILES:
                    truncated = True
                    break
                size = int(entry.get("size", 0))
                if budget + size > settings.MAX_BYTES:
                    truncated = True
                    continue
                budget += size
                selected.append(entry)

            files = await _fetch_files(client, base, sha, selected)
    except httpx.HTTPError as exc:
        logger.warning("GitHub request failed: %s", type(exc).__name__)
        raise GitHubFetchError("Could not reach GitHub. Please try again later.") from exc
    except TimeoutError as exc:
        logger.warning("GitHub fetch timed out overall")
        raise GitHubFetchError("Fetching the repository took too long. Please try again.") from exc

    if not files:
        raise GitHubFetchError("No analysable source files found in this repository.")
    total = (len(readme.encode()) if readme else 0) + sum(len(f.content.encode()) for f in files)
    return RepoSnapshotData(
        owner=owner,
        repo=repo,
        commit_sha=sha,
        file_tree=file_tree,
        readme=readme,
        files=files,
        total_bytes=total,
        truncated=truncated,
        fork=bool(info.get("fork")),
        archived=bool(info.get("archived")),
    )


async def _fetch_files(
    client: httpx.AsyncClient, base: str, sha: str, selected: list[dict[str, Any]]
) -> list[SnapshotFile]:
    """Fetch selected files concurrently (bounded), keeping priority order."""
    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(entry: dict[str, Any]) -> SnapshotFile | None:
        async with semaphore:
            content = await _fetch_file(client, base, sha, entry["path"])
        return None if content is None else SnapshotFile(path=entry["path"], content=content)

    async with asyncio.timeout(FETCH_TOTAL_TIMEOUT):
        tasks = [asyncio.create_task(one(e)) for e in selected]
        try:
            results = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            raise
    return [r for r in results if r is not None]


async def _fetch_readme(client: httpx.AsyncClient, base: str, sha: str) -> str | None:
    resp = await _get(client, f"{GITHUB_API}{base}/readme?ref={sha}", raw=True)
    if resp.status_code == 404:
        return None
    _check(resp)
    return _cap_readme(resp.text)


async def _fetch_file(client: httpx.AsyncClient, base: str, sha: str, path: str) -> str | None:
    url = f"{GITHUB_API}{base}/contents/{quote(path, safe='/')}?ref={sha}"
    resp = await _get(client, url, raw=True)
    if resp.status_code == 404:
        return None
    _check(resp)
    try:
        text = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return None if _looks_binary(text) else text
