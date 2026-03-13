"""Reviews endpoints: list review reply drafts and approve."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, ensure_app_access
from app.models.user import User
from app.models.review_reply import ReviewReply
from app.models.app import App

router = APIRouter()


@router.get("/{app_id}/reviews")
async def list_review_replies(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List review reply drafts for an app."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(ReviewReply)
        .where(ReviewReply.app_id == app_id)
        .where(ReviewReply.status.in_(["pending", "approved"]))
        .order_by(ReviewReply.id.desc())
        .limit(50)
    )
    replies = result.scalars().all()

    return [
        {
            "id": r.id,
            "review_id": r.review_id,
            "reviewer_name": r.reviewer_name,
            "review_text": r.review_text,
            "review_rating": r.review_rating,
            "draft_reply": r.draft_reply,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in replies
    ]


@router.post("/{app_id}/reviews/{reply_id}/approve")
async def approve_review_reply(
    app_id: int,
    reply_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Approve a review reply draft and publish it."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(ReviewReply)
        .where(ReviewReply.id == reply_id)
        .where(ReviewReply.app_id == app_id)
    )
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Review reply not found")

    if reply.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve reply with status={reply.status}",
        )

    reply.status = "approved"
    await db.commit()

    return {
        "status": "approved",
        "reply_id": reply.id,
        "message": "Reply approved. Will be published in next publish window.",
    }
