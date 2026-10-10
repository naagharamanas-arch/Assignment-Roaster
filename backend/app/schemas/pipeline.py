"""Shared contracts between the GitHub fetcher, OpenAI services and job runner."""

from typing import Literal

from pydantic import BaseModel, Field


class SnapshotFile(BaseModel):
    """One source file included in a repo snapshot."""

    path: str
    content: str


class RepoSnapshotData(BaseModel):
    """Trimmed, untrusted view of a GitHub repository."""

    owner: str
    repo: str
    commit_sha: str
    file_tree: list[str]
    readme: str | None = None
    files: list[SnapshotFile] = Field(default_factory=list)
    total_bytes: int = 0
    truncated: bool = False
    fork: bool = False
    archived: bool = False


class CategoryScores(BaseModel):
    """0-100 score per review category."""

    structure: int = Field(ge=0, le=100)
    readme: int = Field(ge=0, le=100)
    code_quality: int = Field(ge=0, le=100)
    tests: int = Field(ge=0, le=100)
    git_hygiene: int = Field(ge=0, le=100)
    security: int = Field(ge=0, le=100)
    originality: int = Field(ge=0, le=100)


class Issue(BaseModel):
    """A concrete problem found in the repo."""

    file: str | None = None
    problem: str
    severity: Literal["low", "medium", "high"]


class AnalysisResult(BaseModel):
    """Structured output of the OpenAI analysis step."""

    score: int = Field(ge=0, le=100)
    categories: CategoryScores
    strengths: list[str]
    issues: list[Issue]
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RoastResult(BaseModel):
    """Structured output of the roast step."""

    title: str
    roast_text: str
    one_liner: str
    fixes: list[str]
    model: str = ""
    moderated_fallback: bool = False
