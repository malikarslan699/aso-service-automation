"""Suggestions endpoints: list, approve, reject, and trigger pipeline."""
import logging
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, ensure_app_access, require_role
from app.models.user import User
from app.models.suggestion import Suggestion
from app.models.global_config import GlobalConfig
from app.models.pipeline_run import PipelineRun
from pydantic import BaseModel
from app.services.listing_publish_queue import (
    list_publish_jobs,
    queue_listing_bundle_for_suggestion,
    retry_listing_bundle_job,
)
from app.services.pipeline_tracking import build_step_log, serialize_step_log, update_step
from app.services.runtime_config import is_true, load_runtime_config, as_int
from app.services.suggestion_tracking import (
    apply_status_log,
    build_publish_response_status,
    build_status_log,
    hydrate_status_log,
    utcnow_naive,
    update_status_stage,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class RejectRequest(BaseModel):
    reason: str


class PipelineTriggerRequest(BaseModel):
    dry_run: bool = True


class RetryPublishRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/{app_id}/suggestions")
async def list_suggestions(
    app_id: int,
    status_filter: Optional[str] = Query(None, alias="status"),
    suggestion_type: Optional[str] = None,
    pipeline_run_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List suggestions for an app, with optional status and type filters."""
    await ensure_app_access(db, user, app_id)
    query = select(Suggestion).where(Suggestion.app_id == app_id)

    if status_filter:
        query = query.where(Suggestion.status == status_filter)
    if suggestion_type:
        query = query.where(Suggestion.suggestion_type == suggestion_type)
    if pipeline_run_id is not None:
        query = query.where(Suggestion.pipeline_run_id == pipeline_run_id)

    query = query.order_by(Suggestion.pipeline_run_id.is_(None), Suggestion.pipeline_run_id.desc(), Suggestion.id.desc()).limit(200)
    result = await db.execute(query)
    suggestions = result.scalars().all()

    payload = []
    for s in suggestions:
        status_log = hydrate_status_log(s)
        response_status = build_publish_response_status(s)
        extra_data = {}
        try:
            extra_data = json.loads(getattr(s, "extra_data", "{}") or "{}")
        except Exception:
            extra_data = {}
        payload.append(
            {
                "id": s.id,
                "pipeline_run_id": s.pipeline_run_id,
                "suggestion_type": s.suggestion_type,
                "field_name": s.field_name,
                "old_value": s.old_value,
                "new_value": s.new_value,
                "reasoning": s.reasoning,
                "risk_score": s.risk_score,
                "status": s.status,
                "review_status": response_status["review_status"],
                "publish_status": response_status["publish_status"],
                "publish_message": s.publish_message,
                "publish_started_at": s.publish_started_at.isoformat() if s.publish_started_at else None,
                "publish_completed_at": s.publish_completed_at.isoformat() if s.publish_completed_at else None,
                "published_live": response_status["published_live"],
                "is_dry_run_result": response_status["is_dry_run_result"],
                "merged_into_job_id": s.merged_into_job_id,
                "dispatch_window": s.dispatch_window,
                "next_eligible_at": s.next_eligible_at.isoformat() if s.next_eligible_at else None,
                "publish_block_reason": s.publish_block_reason,
                "publish_error_code": _extract_publish_error_code(s.publish_message, s.publish_block_reason),
                "review_id": extra_data.get("review_id") if s.suggestion_type == "review_reply" else None,
                "extra_data": extra_data if s.suggestion_type == "review_reply" else {},
                "reviewed_by": s.reviewed_by,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_transition_at": s.last_transition_at.isoformat() if s.last_transition_at else None,
                "status_log": status_log,
            }
        )

    return payload


def _extract_publish_error_code(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        text = value.strip()
        if text.startswith("[") and "]" in text:
            return text[1:text.find("]")]
    return None


@router.post("/{app_id}/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    app_id: int,
    suggestion_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Approve a suggestion and schedule it for publishing."""
    await ensure_app_access(db, user, app_id)
    suggestion = await _get_suggestion(app_id, suggestion_id, db)

    if suggestion.status not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve suggestion with status={suggestion.status}",
        )

    suggestion.status = "approved"
    suggestion.reviewed_by = user.username
    suggestion.last_transition_at = utcnow_naive()

    from app.workers.celery_app import celery_app
    publish_after_approval = True
    dry_run_enabled = True
    config = await db.run_sync(load_runtime_config)
    publish_after_approval = is_true(config.get("publish_after_approval"), True)
    dry_run_enabled = is_true(config.get("dry_run"), True)

    is_listing = suggestion.suggestion_type == "listing"
    suggestion.publish_status = "queued_bundle" if publish_after_approval and is_listing else "queued" if publish_after_approval else "ready"
    suggestion.publish_message = (
        "Approved and added to paced listing bundle queue."
        if publish_after_approval and is_listing
        else "Approved and queued for dry-run publish simulation."
        if publish_after_approval and dry_run_enabled
        else "Approved and queued for Google publish."
        if publish_after_approval
        else "Approved and ready to publish in Google when live mode is enabled."
    )
    suggestion.publish_started_at = None
    suggestion.publish_completed_at = None
    suggestion.published_live = False
    suggestion.is_dry_run_result = False
    suggestion.publish_block_reason = None
    status_log = hydrate_status_log(suggestion)
    status_log = update_status_stage(
        status_log,
        "reviewed",
        status="completed",
        message=f"Approved by {user.username}",
        actor=user.username,
        occurred_at=suggestion.last_transition_at,
    )
    if publish_after_approval and not is_listing:
        status_log = update_status_stage(
            status_log,
            "queued_for_publish",
            status="completed",
            message=suggestion.publish_message,
            actor="system",
            occurred_at=suggestion.last_transition_at,
        )
    else:
        status_log = update_status_stage(
            status_log,
            "queued_for_publish",
            status="pending",
            message=suggestion.publish_message,
            actor="system",
            occurred_at=suggestion.last_transition_at,
        )
    apply_status_log(suggestion, status_log)

    await db.commit()

    bundle_result = None

    try:
        if publish_after_approval:
            if is_listing:
                bundle_result = await db.run_sync(
                    lambda sync_db: queue_listing_bundle_for_suggestion(
                        sync_db,
                        app_id=app_id,
                        suggestion_id=suggestion.id,
                        actor=user.username,
                    )
                )
            else:
                celery_app.send_task(
                    "publish_suggestion",
                    kwargs={"suggestion_id": suggestion.id, "app_id": app_id},
                    ignore_result=True,
                )
    except Exception as exc:
        logger.warning("Failed to queue publish task for suggestion %s: %s", suggestion.id, exc)

    await db.refresh(suggestion)

    # Update auto-approve learning
    from app.services.auto_approve_engine import update_rules as _update_rules

    await db.run_sync(
        lambda sync_db: _update_rules(suggestion.suggestion_type, "approved", app_id, sync_db)
    )

    return {
        "status": "approved",
        "suggestion_id": suggestion.id,
        "publish_queued": publish_after_approval,
        "publish_status": suggestion.publish_status,
        "publish_job_id": suggestion.merged_into_job_id,
        "next_eligible_at": suggestion.next_eligible_at.isoformat() if suggestion.next_eligible_at else None,
        "dispatch_window": suggestion.dispatch_window,
        "message": suggestion.publish_message,
        "bundle_status": bundle_result.get("status") if bundle_result else None,
    }


@router.post("/{app_id}/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    app_id: int,
    suggestion_id: int,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Reject a suggestion with a reason."""
    await ensure_app_access(db, user, app_id)
    suggestion = await _get_suggestion(app_id, suggestion_id, db)

    if suggestion.status not in ("pending",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject suggestion with status={suggestion.status}",
        )

    suggestion.status = "rejected"
    suggestion.reviewed_by = user.username
    suggestion.reasoning = f"Rejected: {body.reason}\n\n(Original: {suggestion.reasoning})"
    suggestion.publish_status = "blocked"
    suggestion.publish_message = "Rejected in review. Not sent to Google publish flow."
    suggestion.publish_block_reason = suggestion.publish_message
    suggestion.last_transition_at = utcnow_naive()
    status_log = hydrate_status_log(suggestion)
    status_log = update_status_stage(
        status_log,
        "reviewed",
        status="completed",
        message=f"Rejected by {user.username}: {body.reason}",
        actor=user.username,
        occurred_at=suggestion.last_transition_at,
    )
    status_log = update_status_stage(
        status_log,
        "publish_result",
        status="blocked",
        message=suggestion.publish_message,
        actor=user.username,
        occurred_at=suggestion.last_transition_at,
    )
    apply_status_log(suggestion, status_log)

    await db.commit()

    # Update auto-approve learning
    from app.services.auto_approve_engine import update_rules as _update_rules

    await db.run_sync(
        lambda sync_db: _update_rules(suggestion.suggestion_type, "rejected", app_id, sync_db)
    )

    return {"status": "rejected", "suggestion_id": suggestion.id}


@router.get("/{app_id}/publish-jobs")
async def get_listing_publish_jobs(
    app_id: int,
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List listing publish bundle jobs for an app."""
    await ensure_app_access(db, user, app_id)
    jobs = await db.run_sync(lambda sync_db: list_publish_jobs(sync_db, app_id=app_id, limit=limit))
    return {"items": jobs}


@router.post("/{app_id}/publish-jobs/{job_id}/retry")
async def retry_listing_publish_job(
    app_id: int,
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Retry a blocked/failed listing bundle job (admin only)."""
    await ensure_app_access(db, user, app_id)
    result = await db.run_sync(
        lambda sync_db: retry_listing_bundle_job(
            sync_db,
            app_id=app_id,
            job_id=job_id,
            actor=user.username,
        )
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result["message"])
    if result.get("status") == "invalid_state":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{app_id}/suggestions/{suggestion_id}/retry-publish")
async def retry_suggestion_publish(
    app_id: int,
    suggestion_id: int,
    body: RetryPublishRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Retry a blocked/failed suggestion publish through paced queue (admin only)."""
    await ensure_app_access(db, user, app_id)
    suggestion = await _get_suggestion(app_id, suggestion_id, db)

    if suggestion.publish_status not in {"blocked", "failed", "superseded", "dry_run_only"}:
        raise HTTPException(
            status_code=400,
            detail=f"Retry is only allowed for blocked/failed/superseded suggestions (current={suggestion.publish_status})",
        )
    if suggestion.status == "rejected":
        raise HTTPException(status_code=400, detail="Rejected suggestions cannot be retried")

    suggestion.status = "approved"
    suggestion.publish_status = "ready"
    suggestion.publish_message = body.reason or "Retry requested by admin. Re-entering paced queue."
    suggestion.publish_block_reason = None
    suggestion.publish_completed_at = None
    suggestion.last_transition_at = utcnow_naive()
    await db.commit()

    if suggestion.suggestion_type == "listing":
        result = await db.run_sync(
            lambda sync_db: queue_listing_bundle_for_suggestion(
                sync_db,
                app_id=app_id,
                suggestion_id=suggestion.id,
                actor=user.username,
            )
        )
        await db.refresh(suggestion)
        return {
            "status": result.get("status"),
            "suggestion_id": suggestion.id,
            "publish_status": suggestion.publish_status,
            "publish_job_id": suggestion.merged_into_job_id,
            "next_eligible_at": suggestion.next_eligible_at.isoformat() if suggestion.next_eligible_at else None,
            "message": suggestion.publish_message,
        }

    from app.workers.celery_app import celery_app

    celery_app.send_task(
        "publish_suggestion",
        kwargs={"suggestion_id": suggestion.id, "app_id": app_id},
        ignore_result=True,
    )
    suggestion.publish_status = "queued"
    suggestion.publish_message = "Retry queued for review reply publish."
    suggestion.last_transition_at = utcnow_naive()
    await db.commit()
    return {
        "status": "queued",
        "suggestion_id": suggestion.id,
        "publish_status": suggestion.publish_status,
        "message": suggestion.publish_message,
    }


@router.post("/{app_id}/pipeline/trigger")
async def trigger_pipeline(
    app_id: int,
    body: PipelineTriggerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Manually trigger the ASO pipeline for an app."""
    await ensure_app_access(db, user, app_id)
    await _expire_stale_queued_runs(app_id, db)
    running_run = await _get_running_pipeline(app_id, db)
    if running_run:
        return {
            "status": "blocked_running",
            "app_id": app_id,
            "message": "A pipeline is already queued or running for this project.",
            "pipeline_run_id": running_run.id,
            "started_at": running_run.started_at.isoformat() if running_run.started_at else None,
        }

    cooldown_minutes = await _manual_trigger_cooldown_minutes(db)
    recent_run = await _get_recent_manual_pipeline(app_id, cooldown_minutes, db)
    if recent_run:
        next_allowed_at = _normalize_utc(recent_run.started_at) + timedelta(minutes=cooldown_minutes)
        return {
            "status": "blocked_cooldown",
            "app_id": app_id,
            "message": f"Run now is cooling down for {cooldown_minutes} minute(s) after the last manual run.",
            "pipeline_run_id": recent_run.id,
            "cooldown_minutes": cooldown_minutes,
            "next_allowed_at": next_allowed_at.isoformat(),
        }

    from app.workers.celery_app import celery_app
    config = await db.run_sync(load_runtime_config)
    dry_run_enabled = is_true(config.get("dry_run"), True)
    manual_approval_required = is_true(config.get("manual_approval_required"), True)

    pipeline_run = PipelineRun(
        app_id=app_id,
        status="queued",
        trigger="manual",
        steps_completed=0,
        total_steps=9,
        started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        step_log=serialize_step_log(
            update_step(build_step_log(), "queue_accepted", status="completed", message="Manual run accepted and waiting for worker pickup")
        ),
    )
    db.add(pipeline_run)
    await db.commit()
    await db.refresh(pipeline_run)

    try:
        task = celery_app.send_task(
            "daily_pipeline",
            args=[app_id],
            kwargs={"trigger": "manual", "pipeline_run_id": pipeline_run.id},
            ignore_result=True,
        )
    except Exception as exc:
        pipeline_run.status = "failed"
        pipeline_run.error_message = str(exc)[:1000]
        pipeline_run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        raise HTTPException(status_code=500, detail="Could not queue pipeline task") from exc

    return {
        "status": "queued",
        "task_id": task.id,
        "app_id": app_id,
        "pipeline_run_id": pipeline_run.id,
        "dry_run": dry_run_enabled,
        "requested_dry_run": body.dry_run,
        "message": "Pipeline queued. Smart duplicate checks will run before any new suggestions are stored.",
        "execution_mode": "demo" if dry_run_enabled else "live",
        "workflow_mode": "manual_approval" if manual_approval_required else "auto_rules",
    }


async def _get_suggestion(app_id: int, suggestion_id: int, db: AsyncSession) -> Suggestion:
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.id == suggestion_id)
        .where(Suggestion.app_id == app_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return s


async def _get_running_pipeline(app_id: int, db: AsyncSession) -> Optional[PipelineRun]:
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.app_id == app_id)
        .where(PipelineRun.status.in_(("queued", "running")))
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _manual_trigger_cooldown_minutes(db: AsyncSession) -> int:
    config = await db.run_sync(load_runtime_config)
    return max(as_int(config.get("manual_trigger_cooldown_minutes"), 15), 0)


async def _get_recent_manual_pipeline(app_id: int, cooldown_minutes: int, db: AsyncSession) -> Optional[PipelineRun]:
    if cooldown_minutes <= 0:
        return None

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=cooldown_minutes)
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.app_id == app_id)
        .where(PipelineRun.trigger == "manual")
        .where(PipelineRun.status.in_(("queued", "running", "completed", "completed_with_warnings", "skipped")))
        .where(PipelineRun.started_at >= cutoff)
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _normalize_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _expire_stale_queued_runs(app_id: int, db: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.app_id == app_id)
        .where(PipelineRun.status == "queued")
        .where(PipelineRun.steps_completed == 0)
        .where(PipelineRun.started_at < cutoff)
    )
    stale_runs = result.scalars().all()
    if not stale_runs:
        return

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for run in stale_runs:
        run.status = "failed"
        run.error_message = "Queue timeout: worker did not start this pipeline."
        run.completed_at = now
        run.step_log = serialize_step_log(
            update_step(build_step_log(), "finalization", status="failed", message=run.error_message)
        )
    await db.commit()
