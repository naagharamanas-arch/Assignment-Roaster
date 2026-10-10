"""Roast endpoints: public share view and visibility toggle."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.exceptions import NotFoundError
from app.models import Analysis, Roast, Submission, User
from app.schemas.submission import PublicRoastOut, RoastOut, VisibilityUpdate

router = APIRouter(prefix="/roasts", tags=["roasts"])


@router.get("/{share_slug}", response_model=PublicRoastOut)
async def get_public_roast(share_slug: str, db: Session = Depends(get_db)) -> PublicRoastOut:
    """Return a shared roast. No auth; 404 unless the owner made it public."""
    roast = db.execute(select(Roast).where(Roast.share_slug == share_slug)).scalars().first()
    if roast is None or not roast.is_public:
        raise NotFoundError("Roast not found")
    sub = db.get(Submission, roast.submission_id)
    analysis = (
        db.execute(
            select(Analysis)
            .where(Analysis.submission_id == roast.submission_id)
            .order_by(Analysis.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return PublicRoastOut(
        title=roast.title,
        roast_text=roast.roast_text,
        one_liner=roast.one_liner,
        fixes=list(roast.fixes),
        score=analysis.score if analysis else None,
        categories=analysis.categories if analysis else None,
        owner=sub.owner if sub else "",
        repo=sub.repo if sub else "",
        created_at=roast.created_at,
    )


@router.put("/{roast_id}/visibility", response_model=RoastOut)
async def set_visibility(
    roast_id: int,
    payload: VisibilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Roast:
    """Toggle public sharing of a roast (owner only)."""
    roast = db.get(Roast, roast_id)
    sub = db.get(Submission, roast.submission_id) if roast else None
    if roast is None or sub is None or sub.user_id != user.id:
        raise NotFoundError("Roast not found")
    roast.is_public = payload.is_public
    db.commit()
    db.refresh(roast)
    return roast
