"""Keywords endpoints: list, competitor analysis, discovery trigger."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, ensure_app_access
from app.models.user import User
from app.models.keyword import Keyword
from app.models.app import App

router = APIRouter()


@router.get("/{app_id}/keywords")
async def list_keywords(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tracked keywords for an app, sorted by opportunity score."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(Keyword)
        .where(Keyword.app_id == app_id)
        .where(Keyword.status == "active")
        .order_by(Keyword.opportunity_score.desc())
        .limit(100)
    )
    keywords = result.scalars().all()

    return [
        {
            "id": kw.id,
            "keyword": kw.keyword,
            "opportunity_score": kw.opportunity_score,
            "volume_signal": kw.volume_signal,
            "competition_signal": kw.competition_signal,
            "source": kw.source,
            "cluster": kw.cluster,
            "rank_position": kw.rank_position,
            "updated_at": kw.updated_at.isoformat() if kw.updated_at else None,
        }
        for kw in keywords
    ]


@router.get("/{app_id}/keywords/competitors")
async def get_competitor_keywords(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get keywords sourced from competitor analysis."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(Keyword)
        .where(Keyword.app_id == app_id)
        .where(Keyword.source.contains("competitor"))
        .where(Keyword.status == "active")
        .order_by(Keyword.opportunity_score.desc())
        .limit(50)
    )
    keywords = result.scalars().all()

    return {
        "competitor_keywords": [
            {
                "keyword": kw.keyword,
                "opportunity_score": kw.opportunity_score,
                "source": kw.source,
                "cluster": kw.cluster,
            }
            for kw in keywords
        ],
        "total": len(keywords),
    }


@router.post("/{app_id}/keywords/discover")
async def trigger_keyword_discovery(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Manually trigger AI keyword discovery for an app."""
    app = await ensure_app_access(db, user, app_id)

    # Trigger via Celery pipeline (keyword discovery is step 2 of daily pipeline)
    from app.workers.celery_app import celery_app
    task = celery_app.send_task("daily_pipeline", args=[app_id], kwargs={"trigger": "keyword_discovery"})

    return {
        "status": "queued",
        "task_id": task.id,
        "app_id": app_id,
        "message": "Keyword discovery will run as part of the pipeline",
    }
