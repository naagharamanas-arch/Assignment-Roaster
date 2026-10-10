"""Background jobs: the submission pipeline and roast regeneration."""

import asyncio
import datetime as dt
import logging
import secrets

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.exceptions import AppError
from app.models import Analysis, RepoSnapshot, Roast, Submission, SubmissionStatus
from app.schemas.pipeline import (
    AnalysisResult,
    CategoryScores,
    Issue,
    RepoSnapshotData,
    RoastResult,
)
from app.services import github_client, usage_service

logger = logging.getLogger(__name__)

STALE_ERROR = "This job took too long and was stopped. Your roast was refunded; please try again."
TIMEOUT_ERROR = "This job timed out. Your roast was refunded; please try again."
REAP_INTERVAL_SECONDS = 120
ACTIVE_STATUSES = (
    SubmissionStatus.queued,
    SubmissionStatus.fetching,
    SubmissionStatus.analysing,
    SubmissionStatus.roasting,
)

_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None

GENERIC_ERROR = "Something went wrong while roasting this repo. Please try again later."


def analysis_to_result(analysis: Analysis) -> AnalysisResult:
    """Rebuild the pipeline AnalysisResult from a stored Analysis row."""
    return AnalysisResult(
        score=analysis.score,
        categories=CategoryScores(**analysis.categories),
        strengths=list(analysis.strengths),
        issues=[Issue(**i) for i in analysis.issues],
        model=analysis.model,
        prompt_tokens=analysis.prompt_tokens,
        completion_tokens=analysis.completion_tokens,
    )


def _new_analysis(submission_id: int, result: AnalysisResult) -> Analysis:
    return Analysis(
        submission_id=submission_id,
        model=result.model or "unknown",
        score=result.score,
        categories=result.categories.model_dump(),
        strengths=result.strengths,
        issues=[i.model_dump() for i in result.issues],
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def _new_roast(submission_id: int, result: RoastResult) -> Roast:
    return Roast(
        submission_id=submission_id,
        title=result.title[:200],
        roast_text=result.roast_text,
        one_liner=result.one_liner[:300] if result.one_liner else None,
        fixes=result.fixes,
        model=result.model or "unknown",
        share_slug=secrets.token_urlsafe(9),
        is_public=False,
    )


def _find_cached_analysis(db: Session, sub: Submission, snap: RepoSnapshotData) -> Analysis | None:
    """Reuse an analysis of the same (owner, repo, commit_sha, brief) from any submission."""
    stmt = (
        select(Analysis)
        .join(Submission, Submission.id == Analysis.submission_id)
        .where(
            Submission.owner == snap.owner,
            Submission.repo == snap.repo,
            Submission.commit_sha == snap.commit_sha,
            Submission.id != sub.id,
        )
        .order_by(Analysis.id.desc())
    )
    if sub.assignment_brief is None:
        stmt = stmt.where(Submission.assignment_brief.is_(None))
    else:
        stmt = stmt.where(Submission.assignment_brief == sub.assignment_brief)
    return db.execute(stmt.limit(1)).scalars().first()


def _get_semaphore() -> asyncio.Semaphore:
    """Return the pipeline semaphore, created lazily on the running event loop."""
    global _semaphore, _semaphore_loop
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore_loop is not loop:
        _semaphore = asyncio.Semaphore(settings.PIPELINE_CONCURRENCY)
        _semaphore_loop = loop
    return _semaphore


def _add_roast(db: Session, submission_id: int, result: RoastResult) -> None:
    """Add a new Roast; earlier roasts of the submission stop being public (share privacy)."""
    db.execute(update(Roast).where(Roast.submission_id == submission_id).values(is_public=False))
    db.add(_new_roast(submission_id, result))


def _fail(
    db: Session,
    submission_id: int,
    message: str,
    restore_done: bool = False,
    user_id: int | None = None,
    usage_date: dt.date | None = None,
) -> None:
    """Mark failed (or restore done for regeneration) and refund the charged roast once.

    If the submission was deleted mid-pipeline, refund using the carried user/date.
    """
    db.rollback()
    sub = db.get(Submission, submission_id)
    if sub is None:
        if user_id is not None and usage_date is not None:
            usage_service.refund_roast(db, user_id, usage_date)
            db.commit()
        return
    if sub.usage_date is not None:  # not yet refunded
        usage_service.refund_roast(db, sub.user_id, sub.usage_date)
        sub.usage_date = None
    if restore_done:
        sub.status = SubmissionStatus.done
        sub.error = message
    elif sub.status != SubmissionStatus.failed:
        sub.status = SubmissionStatus.failed
        sub.error = message
    db.commit()


def reap_stale_submissions(db: Session | None = None) -> int:
    """Fail (or restore, for regenerations) jobs stuck in progress; refund each exactly once."""
    own = db is None
    session = db if db is not None else SessionLocal()
    reaped = 0
    try:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=settings.STALE_JOB_MINUTES)
        touched = func.coalesce(Submission.updated_at, Submission.created_at)
        stale = session.execute(
            select(Submission.id, Submission.user_id, Submission.usage_date).where(
                Submission.status.in_(ACTIVE_STATUSES), touched < cutoff
            )
        ).all()
        for sub_id, user_id, usage_date in stale:
            is_regen = (
                session.execute(
                    select(func.count(Roast.id)).where(Roast.submission_id == sub_id)
                ).scalar_one()
                > 0
            )
            values: dict[str, object] = {
                "status": SubmissionStatus.done if is_regen else SubmissionStatus.failed,
                "error": STALE_ERROR,
                "usage_date": None,
            }
            claimed = session.execute(
                update(Submission)
                .where(
                    Submission.id == sub_id,
                    Submission.status.in_(ACTIVE_STATUSES),
                    touched < cutoff,
                )
                .values(**values)
            )
            if claimed.rowcount == 1:  # type: ignore[attr-defined]
                if usage_date is not None:
                    usage_service.refund_roast(session, user_id, usage_date)
                reaped += 1
            session.commit()
        if reaped:
            logger.warning("Reaped %s stale submission(s)", reaped)
        return reaped
    except Exception:
        session.rollback()
        logger.exception("Stale submission reaper failed")
        return reaped
    finally:
        if own:
            session.close()


async def reaper_loop() -> None:
    """Periodically reap stale jobs until cancelled."""
    while True:
        await asyncio.sleep(REAP_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(reap_stale_submissions)
        except Exception:
            logger.exception("Reaper iteration crashed")


async def run_submission_pipeline(submission_id: int) -> None:
    """Run fetch -> analyse -> roast with a concurrency gate and an overall timeout."""
    async with _get_semaphore():
        await _run_submission_pipeline(submission_id)


async def _run_submission_pipeline(submission_id: int) -> None:
    db = SessionLocal()
    user_id: int | None = None
    usage_date: dt.date | None = None
    try:
        sub = db.get(Submission, submission_id)
        if sub is None:
            logger.warning("Submission %s vanished before the pipeline ran", submission_id)
            return
        user_id, usage_date = sub.user_id, sub.usage_date
        await asyncio.wait_for(
            _pipeline_steps(db, submission_id), timeout=settings.PIPELINE_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning("Pipeline timed out for submission %s", submission_id)
        _fail(db, submission_id, TIMEOUT_ERROR, user_id=user_id, usage_date=usage_date)
    except AppError as exc:
        logger.info("Pipeline failed for submission %s: %s", submission_id, exc.detail)
        _fail(db, submission_id, exc.detail, user_id=user_id, usage_date=usage_date)
    except Exception:
        logger.exception("Pipeline crashed for submission %s", submission_id)
        _fail(db, submission_id, GENERIC_ERROR, user_id=user_id, usage_date=usage_date)
    finally:
        db.close()


def _load_active(db: Session, submission_id: int) -> Submission | None:
    """Reload the submission; None if it was deleted or already reaped/refunded."""
    db.expire_all()
    sub = db.get(Submission, submission_id)
    if sub is None or sub.usage_date is None or sub.status == SubmissionStatus.failed:
        return None
    return sub


async def _pipeline_steps(db: Session, submission_id: int) -> None:
    """Pipeline body. The DB transaction is closed before every external await."""
    from app.services import openai_analyzer, roast_writer

    sub = db.get(Submission, submission_id)
    if sub is None:
        return
    repo_url = sub.repo_url
    sub.status = SubmissionStatus.fetching
    db.commit()  # no open transaction while talking to GitHub

    snap = await github_client.fetch_repo_snapshot(repo_url)
    sub = _load_active(db, submission_id)
    if sub is None:
        raise _Abandoned
    sub.commit_sha = snap.commit_sha
    db.add(
        RepoSnapshot(
            submission_id=sub.id,
            file_tree=snap.file_tree,
            readme=snap.readme,
            selected_files=[f.model_dump() for f in snap.files],
            total_bytes=snap.total_bytes,
            truncated=snap.truncated,
        )
    )
    sub.status = SubmissionStatus.analysing
    cached = _find_cached_analysis(db, sub, snap)
    brief = sub.assignment_brief
    level, style = sub.roast_level.value, sub.language_style.value
    result = analysis_to_result(cached) if cached is not None else None
    db.commit()  # release before the LLM call

    if result is None:
        result = await openai_analyzer.analyze_repo(snap, brief)
    sub = _load_active(db, submission_id)
    if sub is None:
        raise _Abandoned
    db.add(_new_analysis(sub.id, result))
    sub.status = SubmissionStatus.roasting
    db.commit()

    roast = await roast_writer.write_roast(result, level, style)
    sub = _load_active(db, submission_id)
    if sub is None:
        raise _Abandoned
    _add_roast(db, sub.id, roast)
    sub.status = SubmissionStatus.done
    sub.error = None
    db.commit()


class _Abandoned(AppError):
    """The submission was deleted or reaped mid-run; refund handled by _fail."""

    default_detail = "Submission no longer active"


async def run_roast_regeneration(submission_id: int) -> None:
    """Create a new Roast from the stored analysis, gated and time-limited."""
    async with _get_semaphore():
        await _run_roast_regeneration(submission_id)


async def _run_roast_regeneration(submission_id: int) -> None:
    from app.services import roast_writer

    db = SessionLocal()
    user_id: int | None = None
    usage_date: dt.date | None = None
    try:
        sub = db.get(Submission, submission_id)
        if sub is None:
            return
        user_id, usage_date = sub.user_id, sub.usage_date
        stored = (
            db.execute(
                select(Analysis)
                .where(Analysis.submission_id == sub.id)
                .order_by(Analysis.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if stored is None:
            raise AppError("No analysis available to roast")
        result = analysis_to_result(stored)
        level, style = sub.roast_level.value, sub.language_style.value
        db.commit()  # close the transaction before the LLM call
        roast = await asyncio.wait_for(
            roast_writer.write_roast(result, level, style),
            timeout=settings.PIPELINE_TIMEOUT_SECONDS,
        )
        sub = _load_active(db, submission_id)
        if sub is None:
            raise _Abandoned
        _add_roast(db, sub.id, roast)
        sub.status = SubmissionStatus.done
        sub.error = None
        db.commit()
    except _Abandoned:
        _fail(db, submission_id, GENERIC_ERROR, True, user_id, usage_date)
    except Exception:
        logger.exception("Roast regeneration failed for submission %s", submission_id)
        _fail(db, submission_id, GENERIC_ERROR, True, user_id, usage_date)
    finally:
        db.close()
