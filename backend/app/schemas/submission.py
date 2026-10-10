"""Request/response schemas for submissions and roasts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import LanguageStyle, RoastLevel, SubmissionStatus


class SubmissionCreate(BaseModel):
    """Payload to submit a repo for roasting."""

    repo_url: str = Field(max_length=300)
    assignment_brief: str | None = Field(default=None, max_length=4000)
    roast_level: RoastLevel = RoastLevel.medium
    language_style: LanguageStyle = LanguageStyle.tamil_script


class RegenerateRequest(BaseModel):
    """Optional new level/style for a regenerated roast."""

    roast_level: RoastLevel | None = None
    language_style: LanguageStyle | None = None


class AnalysisOut(BaseModel):
    """Stored analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    score: int
    categories: dict[str, Any]
    strengths: list[str]
    issues: list[dict[str, Any]]
    model: str


class RoastOut(BaseModel):
    """Roast as seen by its owner."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    roast_text: str
    one_liner: str | None
    fixes: list[str]
    share_slug: str
    is_public: bool
    created_at: datetime


class SubmissionOut(BaseModel):
    """Submission summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_url: str
    owner: str
    repo: str
    commit_sha: str | None
    roast_level: RoastLevel
    language_style: LanguageStyle
    status: SubmissionStatus
    error: str | None
    created_at: datetime
    score: int | None = None


class SubmissionDetail(SubmissionOut):
    """Submission with analysis and latest roast (when done)."""

    assignment_brief: str | None = None
    analysis: AnalysisOut | None = None
    roast: RoastOut | None = None


class VisibilityUpdate(BaseModel):
    """Toggle public sharing."""

    is_public: bool


class PublicRoastOut(BaseModel):
    """Public share view; contains no user or private submission info."""

    title: str
    roast_text: str
    one_liner: str | None
    fixes: list[str]
    score: int | None
    categories: dict[str, Any] | None
    owner: str
    repo: str
    created_at: datetime
