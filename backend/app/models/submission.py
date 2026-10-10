"""Submission model and its enums."""

import datetime as dt
import enum
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Analysis
    from app.models.roast import Roast
    from app.models.snapshot import RepoSnapshot
    from app.models.user import User


class SubmissionStatus(enum.StrEnum):
    """Pipeline status of a submission."""

    queued = "queued"
    fetching = "fetching"
    analysing = "analysing"
    roasting = "roasting"
    done = "done"
    failed = "failed"


class RoastLevel(enum.StrEnum):
    """Roast intensity."""

    mild = "mild"
    medium = "medium"
    savage = "savage"


class LanguageStyle(enum.StrEnum):
    """Roast language style."""

    tamil_script = "tamil_script"
    tanglish = "tanglish"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Submission(Base, TimestampMixin):
    """A GitHub repo submitted for roasting."""

    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_user_id_created_at", "user_id", "created_at"),
        Index("ix_submissions_owner_repo_commit_sha", "owner", "repo", "commit_sha"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    repo: Mapped[str] = mapped_column(String(100), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignment_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    roast_level: Mapped[RoastLevel] = mapped_column(
        Enum(RoastLevel, native_enum=False, length=20, values_callable=_enum_values),
        default=RoastLevel.medium,
        nullable=False,
    )
    language_style: Mapped[LanguageStyle] = mapped_column(
        Enum(LanguageStyle, native_enum=False, length=20, values_callable=_enum_values),
        default=LanguageStyle.tamil_script,
        nullable=False,
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=20, values_callable=_enum_values),
        default=SubmissionStatus.queued,
        nullable=False,
        index=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="submissions")
    snapshot: Mapped["RepoSnapshot | None"] = relationship(
        back_populates="submission", cascade="all, delete-orphan", uselist=False
    )
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    roasts: Mapped[list["Roast"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
