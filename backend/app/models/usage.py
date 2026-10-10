"""UsageCounter and CreditBalance models."""

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class UsageCounter(Base):
    """Per-user per-day roast usage."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_usage_counters_user_id_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    roasts_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="usage_counters")


class CreditBalance(Base, TimestampMixin):
    """Purchased credits (post-MVP)."""

    __tablename__ = "credit_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="credit_balance")
