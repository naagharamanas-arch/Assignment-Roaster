"""Roast model."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.submission import Submission


class Roast(Base, TimestampMixin):
    """Generated roast text with fixes and a public share slug."""

    __tablename__ = "roasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    roast_text: Mapped[str] = mapped_column(Text, nullable=False)
    one_liner: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fixes: Mapped[Any] = mapped_column(JSON, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    share_slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    submission: Mapped["Submission"] = relationship(back_populates="roasts")
