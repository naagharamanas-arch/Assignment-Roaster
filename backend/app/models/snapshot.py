"""RepoSnapshot model."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.submission import Submission


class RepoSnapshot(Base):
    """Trimmed snapshot of a GitHub repo."""

    __tablename__ = "repo_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    file_tree: Mapped[Any] = mapped_column(JSON, nullable=True)
    readme: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_files: Mapped[Any] = mapped_column(JSON, nullable=True)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    submission: Mapped["Submission"] = relationship(back_populates="snapshot")
