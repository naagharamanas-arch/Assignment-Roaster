"""Submission endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.exceptions import AppError, ConflictError, NotFoundError
from app.models import Analysis, Roast, Submission, SubmissionStatus, User
from app.schemas.submission import (
    AnalysisOut,
    RegenerateRequest,
    RoastOut,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionOut,
)
from app.services import jobs, usage_service
from app.services.github_client import parse_repo_url

router = APIRouter(prefix="/submissions", tags=["submissions"])


def _owned(db: Session, submission_id: int, user: User) -> Submission:
    sub = db.get(Submission, submission_id)
    if sub is None or sub.user_id != user.id:
        raise NotFoundError("Submission not found")
    return sub


def _latest_analysis(db: Session, submission_id: int) -> Analysis | None:
    return (
        db.execute(
            select(Analysis)
            .where(Analysis.submission_id == submission_id)
            .order_by(Analysis.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _latest_roast(db: Session, submission_id: int) -> Roast | None:
    return (
        db.execute(
            select(Roast)
            .where(Roast.submission_id == submission_id)
            .order_by(Roast.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


@router.post("", response_model=SubmissionOut, status_code=201)
async def create_submission(
    payload: SubmissionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """Validate the repo URL, enforce limits, and queue the pipeline."""
    owner, repo = parse_repo_url(payload.repo_url)
    usage_service.check_global_capacity(db)
    try:
        # Quota UPDATE first: its row lock serialises this user's concurrent submits, so the
        # cooldown check below sees any committed same-repo submission.
        usage_date = usage_service.consume_roast(db, user.id)
        usage_service.check_repo_cooldown(db, user.id, owner, repo)
    except AppError:
        db.rollback()
        raise
    sub = Submission(
        user_id=user.id,
        repo_url=f"https://github.com/{owner}/{repo}",
        owner=owner,
        repo=repo,
        assignment_brief=payload.assignment_brief or None,
        roast_level=payload.roast_level,
        language_style=payload.language_style,
        status=SubmissionStatus.queued,
        usage_date=usage_date,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    background_tasks.add_task(jobs.run_submission_pipeline, sub.id)
    return sub


@router.get("", response_model=list[SubmissionOut])
async def list_submissions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubmissionOut]:
    """List the current user's submissions, newest first, with the latest score."""
    score = (
        select(Analysis.score)
        .where(Analysis.submission_id == Submission.id)
        .order_by(Analysis.id.desc())
        .limit(1)
        .correlate(Submission)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Submission, score.label("score"))
        .where(Submission.user_id == user.id)
        .order_by(Submission.created_at.desc(), Submission.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    out: list[SubmissionOut] = []
    for sub, latest_score in rows:
        item = SubmissionOut.model_validate(sub)
        item.score = latest_score
        out.append(item)
    return out


@router.get("/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubmissionDetail:
    """Return status plus analysis and latest roast once done."""
    sub = _owned(db, submission_id, user)
    detail = SubmissionDetail.model_validate(sub)
    detail.assignment_brief = sub.assignment_brief
    analysis = _latest_analysis(db, sub.id)
    roast = _latest_roast(db, sub.id)
    if analysis is not None:
        detail.analysis = AnalysisOut.model_validate(analysis)
    if roast is not None and sub.status in (SubmissionStatus.done, SubmissionStatus.roasting):
        detail.roast = RoastOut.model_validate(roast)
    return detail


@router.delete("/{submission_id}", status_code=204)
async def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Delete a submission and everything attached to it."""
    sub = _owned(db, submission_id, user)
    db.delete(sub)
    db.commit()
    return Response(status_code=204)


@router.get("/{submission_id}/analysis", response_model=AnalysisOut)
async def get_analysis(
    submission_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Analysis:
    """Return scores and issues for a submission."""
    sub = _owned(db, submission_id, user)
    analysis = _latest_analysis(db, sub.id)
    if analysis is None:
        raise NotFoundError("Analysis not ready yet")
    return analysis


@router.post("/{submission_id}/roast/regenerate", response_model=SubmissionOut, status_code=202)
async def regenerate_roast(
    submission_id: int,
    background_tasks: BackgroundTasks,
    payload: RegenerateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Submission:
    """Create a new roast from the stored analysis; counts toward the daily limit."""
    sub = _owned(db, submission_id, user)
    if sub.status != SubmissionStatus.done or _latest_analysis(db, sub.id) is None:
        raise ConflictError("Roast can only be regenerated once the submission is done")
    usage_service.check_global_capacity(db)
    sub.usage_date = usage_service.consume_roast(db, user.id)
    sub.error = None
    if payload and payload.roast_level:
        sub.roast_level = payload.roast_level
    if payload and payload.language_style:
        sub.language_style = payload.language_style
    sub.status = SubmissionStatus.roasting
    db.commit()
    db.refresh(sub)
    background_tasks.add_task(jobs.run_roast_regeneration, sub.id)
    return sub
