"""Usage limits: daily roast quota and per-repo hourly submission cap."""

import datetime as dt

from sqlalchemy import Insert, case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import AppError, RateLimitError
from app.models import Submission, SubmissionStatus, UsageCounter

REPO_COOLDOWN = dt.timedelta(hours=1)


class CapacityError(AppError):
    """Global daily capacity reached (503)."""

    status_code = 503
    default_detail = "Daily capacity reached, try tomorrow."


def _today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def _next_reset() -> dt.datetime:
    tomorrow = _today() + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, dt.time.min, tzinfo=dt.UTC)


def _get_counter(db: Session, user_id: int) -> UsageCounter | None:
    return db.execute(
        select(UsageCounter).where(UsageCounter.user_id == user_id, UsageCounter.date == _today())
    ).scalar_one_or_none()


def roasts_used_today(db: Session, user_id: int) -> int:
    """Return how many roasts the user has consumed today (UTC)."""
    counter = _get_counter(db, user_id)
    return counter.roasts_used if counter else 0


def check_daily_limit(db: Session, user_id: int) -> None:
    """Raise RateLimitError (429) if the user has used up today's roasts."""
    if roasts_used_today(db, user_id) >= settings.DAILY_ROAST_LIMIT:
        reset = _next_reset().strftime("%Y-%m-%d %H:%M UTC")
        raise RateLimitError(
            f"Daily limit of {settings.DAILY_ROAST_LIMIT} roasts reached. Resets at {reset}."
        )


def check_repo_cooldown(db: Session, user_id: int, owner: str, repo: str) -> None:
    """Raise RateLimitError (429) if this repo was submitted by the user within the last hour."""
    cutoff = dt.datetime.now(dt.UTC) - REPO_COOLDOWN
    latest = db.execute(
        select(func.max(Submission.created_at)).where(
            Submission.user_id == user_id,
            func.lower(Submission.owner) == owner.lower(),
            func.lower(Submission.repo) == repo.lower(),
            Submission.status != SubmissionStatus.failed,
            Submission.created_at >= cutoff,
        )
    ).scalar_one_or_none()
    if latest is None:
        return
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=dt.UTC)
    minutes = max(1, int((latest + REPO_COOLDOWN - dt.datetime.now(dt.UTC)).total_seconds() // 60))
    raise RateLimitError(
        f"You already submitted this repo recently. Try again in about {minutes} minute(s)."
    )


def _ensure_counter_row(db: Session, user_id: int, day: dt.date) -> None:
    """Insert the (user, day) counter row if missing; a concurrent insert is a no-op."""
    values = {"user_id": user_id, "date": day, "roasts_used": 0}
    stmt: Insert
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        stmt = pg_insert(UsageCounter).values(**values).on_conflict_do_nothing()
    else:
        stmt = sqlite_insert(UsageCounter).values(**values).on_conflict_do_nothing()
    db.execute(stmt)


def check_global_capacity(db: Session) -> None:
    """Raise CapacityError (503) if today's total jobs across all users hit the global cap."""
    total = db.execute(
        select(func.coalesce(func.sum(UsageCounter.roasts_used), 0)).where(
            UsageCounter.date == _today()
        )
    ).scalar_one()
    if int(total) >= settings.GLOBAL_DAILY_JOB_CAP:
        raise CapacityError("Daily capacity reached, try tomorrow.")


def consume_roast(db: Session, user_id: int) -> dt.date:
    """Atomically enforce the daily limit and count one roast; returns the charged date.

    The UPDATE holds a row lock on the user's counter until the caller commits, which
    also serialises concurrent submissions by the same user. Caller commits.
    """
    day = _today()
    _ensure_counter_row(db, user_id, day)
    result = db.execute(
        update(UsageCounter)
        .where(
            UsageCounter.user_id == user_id,
            UsageCounter.date == day,
            UsageCounter.roasts_used < settings.DAILY_ROAST_LIMIT,
        )
        .values(roasts_used=UsageCounter.roasts_used + 1)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        reset = _next_reset().strftime("%Y-%m-%d %H:%M UTC")
        raise RateLimitError(
            f"Daily limit of {settings.DAILY_ROAST_LIMIT} roasts reached. Resets at {reset}."
        )
    return day


def refund_roast(db: Session, user_id: int, usage_date: dt.date | None = None) -> None:
    """Atomically give back one roast on the counter that was charged. Caller commits."""
    db.execute(
        update(UsageCounter)
        .where(UsageCounter.user_id == user_id, UsageCounter.date == (usage_date or _today()))
        .values(
            roasts_used=case((UsageCounter.roasts_used > 0, UsageCounter.roasts_used - 1), else_=0)
        )
    )
