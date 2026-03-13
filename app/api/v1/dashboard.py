"""Dashboard endpoint: pipeline status, health, and summary."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.pipeline_run import PipelineRun
from app.models.suggestion import Suggestion
from app.models.keyword import Keyword
from app.models.app import App
from app.models.user_app_access import UserAppAccess
from app.services.pipeline_tracking import current_step_label, parse_step_log

router = APIRouter()


@router.get("")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return dashboard summary: latest pipeline runs, suggestion counts, health."""

    # Latest pipeline run per app
    app_query = select(App).order_by(App.id)
    if user.role == "sub_admin":
        app_query = (
            select(App)
            .join(UserAppAccess, UserAppAccess.app_id == App.id)
            .where(UserAppAccess.user_id == user.id)
            .order_by(App.id)
        )
    apps_result = await db.execute(app_query)
    apps = apps_result.scalars().all()

    pipeline_summaries = []
    for app in apps:
        latest_run = await db.execute(
            select(PipelineRun)
            .where(PipelineRun.app_id == app.id)
            .order_by(PipelineRun.id.desc())
            .limit(1)
        )
        run = latest_run.scalar_one_or_none()

        approved_count_result = await db.execute(
            select(func.count()).select_from(Suggestion)
            .where(Suggestion.app_id == app.id)
            .where(Suggestion.status == "approved")
        )
        approved_count = approved_count_result.scalar() or 0

        pending_count_result = await db.execute(
            select(func.count()).select_from(Suggestion)
            .where(Suggestion.app_id == app.id)
            .where(Suggestion.status == "pending")
        )
        pending_count = pending_count_result.scalar() or 0

        keywords_count_result = await db.execute(
            select(func.count()).select_from(Keyword)
            .where(Keyword.app_id == app.id)
            .where(Keyword.status == "active")
        )
        keywords_count = keywords_count_result.scalar() or 0

        step_log = parse_step_log(run.step_log if run else None)
        current_label = current_step_label(step_log, run.error_message if run else None)

        pipeline_summaries.append({
            "app_id": app.id,
            "app_name": app.name,
            "package_name": app.package_name,
            "app_status": app.status,
            "pending_suggestions": pending_count,
            "approved_suggestions": approved_count,
            "active_keywords": keywords_count,
            "last_pipeline": {
                "id": run.id if run else None,
                "status": run.status if run else "never_run",
                "overall_status": run.status if run else "never_run",
                "trigger": run.trigger if run else None,
                "steps_completed": run.steps_completed if run else 0,
                "total_steps": run.total_steps if run else 0,
                "suggestions_generated": run.suggestions_generated if run else 0,
                "duplicates_skipped": run.duplicates_skipped if run else 0,
                "keywords_discovered": run.keywords_discovered if run else 0,
                "approvals_created": run.approvals_created if run else 0,
                "provider_name": run.provider_name if run else None,
                "fallback_provider_name": run.fallback_provider_name if run else None,
                "provider_status": run.provider_status if run else None,
                "provider_error_class": run.provider_error_class if run else None,
                "estimated_cost": run.estimated_cost if run else 0.0,
                "input_tokens": run.input_tokens if run else 0,
                "output_tokens": run.output_tokens if run else 0,
                "value_summary": run.value_summary if run else None,
                "current_step_label": current_label,
                "step_log": step_log,
                "error_message": run.error_message if run else None,
                "started_at": run.started_at.isoformat() if run and run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run and run.completed_at else None,
            } if run else None,
        })

    # Overall counts
    total_pending_result = await db.execute(
        select(func.count()).select_from(Suggestion).where(Suggestion.status == "pending")
    )
    total_pending = total_pending_result.scalar() or 0

    return {
        "apps": pipeline_summaries,
        "total_pending_suggestions": total_pending,
        "health": {
            "database": "ok",
            "api": "ok",
        },
    }
