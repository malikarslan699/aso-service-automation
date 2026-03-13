"""Dashboard endpoint: pipeline status, health, and summary."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.pipeline_run import PipelineRun
from app.models.suggestion import Suggestion
from app.models.keyword import Keyword
from app.models.app import App
from app.models.user_app_access import UserAppAccess
from app.services.pipeline_tracking import current_step_label, parse_step_log
from app.services.runtime_config import is_true, load_runtime_config

router = APIRouter()


@router.get("")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return dashboard summary: latest pipeline runs, suggestion counts, health, and mode flags."""

    # --- Load apps accessible to this user ---
    app_query = select(App).order_by(App.id)
    if user.role in {"admin", "sub_admin"}:
        app_query = (
            select(App)
            .outerjoin(
                UserAppAccess,
                (UserAppAccess.app_id == App.id) & (UserAppAccess.user_id == user.id),
            )
            .where(or_(App.owner_user_id == user.id, UserAppAccess.user_id == user.id))
            .order_by(App.id)
            .distinct()
        )
    apps_result = await db.execute(app_query)
    apps = apps_result.scalars().all()
    app_ids = [a.id for a in apps]

    if not app_ids:
        return {
            "apps": [],
            "total_pending_suggestions": 0,
            "health": {"database": "ok", "api": "ok"},
            "mode": {"dry_run": True, "manual_approval_required": True},
        }

    # --- Bulk: latest pipeline run per app (one query) ---
    latest_run_subq = (
        select(func.max(PipelineRun.id).label("max_id"))
        .where(PipelineRun.app_id.in_(app_ids))
        .group_by(PipelineRun.app_id)
        .subquery()
    )
    runs_result = await db.execute(
        select(PipelineRun).where(PipelineRun.id.in_(select(latest_run_subq.c.max_id)))
    )
    runs_by_app: dict[int, PipelineRun] = {r.app_id: r for r in runs_result.scalars().all()}

    # --- Bulk: pending suggestion counts per app ---
    pending_result = await db.execute(
        select(Suggestion.app_id, func.count().label("cnt"))
        .where(Suggestion.app_id.in_(app_ids))
        .where(Suggestion.status == "pending")
        .group_by(Suggestion.app_id)
    )
    pending_by_app: dict[int, int] = {row.app_id: row.cnt for row in pending_result}

    # --- Bulk: approved suggestion counts per app ---
    approved_result = await db.execute(
        select(Suggestion.app_id, func.count().label("cnt"))
        .where(Suggestion.app_id.in_(app_ids))
        .where(Suggestion.status == "approved")
        .group_by(Suggestion.app_id)
    )
    approved_by_app: dict[int, int] = {row.app_id: row.cnt for row in approved_result}

    # --- Bulk: active keyword counts per app ---
    kw_result = await db.execute(
        select(Keyword.app_id, func.count().label("cnt"))
        .where(Keyword.app_id.in_(app_ids))
        .where(Keyword.status == "active")
        .group_by(Keyword.app_id)
    )
    keywords_by_app: dict[int, int] = {row.app_id: row.cnt for row in kw_result}

    # --- Mode flags from runtime config ---
    config = await db.run_sync(load_runtime_config)
    dry_run_mode = is_true(config.get("dry_run"), True)
    manual_approval_required = is_true(config.get("manual_approval_required"), True)

    # --- Build per-app summaries ---
    pipeline_summaries = []
    for app in apps:
        run = runs_by_app.get(app.id)
        step_log = parse_step_log(run.step_log if run else None)
        current_label = current_step_label(step_log, run.error_message if run else None)

        pipeline_summaries.append({
            "app_id": app.id,
            "app_name": app.name,
            "package_name": app.package_name,
            "app_status": app.status,
            "pending_suggestions": pending_by_app.get(app.id, 0),
            "approved_suggestions": approved_by_app.get(app.id, 0),
            "active_keywords": keywords_by_app.get(app.id, 0),
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

    total_pending = sum(pending_by_app.get(aid, 0) for aid in app_ids)

    return {
        "apps": pipeline_summaries,
        "total_pending_suggestions": total_pending,
        "health": {"database": "ok", "api": "ok"},
        "mode": {
            "dry_run": dry_run_mode,
            "manual_approval_required": manual_approval_required,
        },
    }
