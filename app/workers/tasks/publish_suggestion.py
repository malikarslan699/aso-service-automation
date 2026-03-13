"""Background publish task for manually approved suggestions."""
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="publish_suggestion")
def publish_suggestion_task(suggestion_id: int, app_id: int):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.app import App
    from app.models.app_credential import AppCredential
    from app.models.suggestion import Suggestion
    from app.models.system_log import SystemLog
    from app.services import execution
    from app.services.publish_guard import recent_live_publish_block_reason
    from app.services.runtime_config import is_true, load_runtime_config
    from app.services.suggestion_tracking import apply_status_log, parse_status_log, update_status_stage, utcnow_naive
    from app.utils.encryption import decrypt_value

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as db:
        def _safe_execute(statement):
            try:
                return db.execute(statement)
            except Exception:
                db.rollback()
                raise

        def _safe_commit() -> None:
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

        suggestion = _safe_execute(
            select(Suggestion)
            .where(Suggestion.id == suggestion_id)
            .where(Suggestion.app_id == app_id)
        ).scalar_one_or_none()
        if suggestion is None:
            return {"status": "skipped", "reason": "suggestion not found"}

        if suggestion.status != "approved":
            return {"status": "skipped", "reason": f"status={suggestion.status}"}

        if suggestion.suggestion_type == "listing":
            from app.services.listing_publish_queue import queue_listing_bundle_for_suggestion

            result = queue_listing_bundle_for_suggestion(
                db,
                app_id=app_id,
                suggestion_id=suggestion.id,
                actor="system",
            )
            return {
                "status": result.get("status", "queued_bundle"),
                "reason": result.get("message", "Listing suggestion moved to paced listing bundle queue"),
                "job_id": result.get("job_id"),
            }

        app = _safe_execute(select(App).where(App.id == app_id)).scalar_one_or_none()
        if app is None:
            return {"status": "skipped", "reason": "app not found"}

        config = load_runtime_config(db)
        dry_run = is_true(config.get("dry_run"), settings.dry_run)
        publish_started_at = utcnow_naive()
        suggestion.publish_started_at = publish_started_at
        suggestion.publish_completed_at = None
        suggestion.last_transition_at = publish_started_at
        suggestion.publish_status = "publishing"
        suggestion.publish_message = (
            "Dry-run publish simulation started."
            if dry_run
            else "Google publish started."
        )
        suggestion.publish_block_reason = None
        status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
        status_log = update_status_stage(
            status_log,
            "publish_attempted",
            status="running",
            message=suggestion.publish_message,
            actor="system",
            occurred_at=publish_started_at,
        )
        apply_status_log(suggestion, status_log)
        _safe_commit()

        allowed, reason = execution.can_publish(app_id, db, publish_kind="review_reply")
        if not allowed:
            blocked_at = utcnow_naive()
            suggestion.publish_status = "blocked"
            suggestion.publish_message = reason
            suggestion.publish_block_reason = reason
            suggestion.publish_completed_at = blocked_at
            suggestion.last_transition_at = blocked_at
            status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
            status_log = update_status_stage(
                status_log,
                "waiting_safe_window",
                status="blocked",
                message=reason,
                actor="system",
                occurred_at=blocked_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_result",
                status="blocked",
                message=reason,
                actor="system",
                occurred_at=blocked_at,
            )
            apply_status_log(suggestion, status_log)
            db.add(SystemLog(level="warning", module="publish_suggestion", message=reason, app_id=app_id))
            _safe_commit()
            return {"status": "blocked", "reason": reason}

        cred_row = _safe_execute(
            select(AppCredential)
            .where(AppCredential.app_id == app_id)
            .where(AppCredential.credential_type == "service_account_json")
        ).scalar_one_or_none()

        credential_json = None
        if cred_row is not None:
            try:
                credential_json = decrypt_value(cred_row.value)
            except Exception:
                credential_json = None

        if not dry_run and credential_json is None:
            blocked_at = utcnow_naive()
            reason = "Missing Google Play credential. Live publish could not start."
            suggestion.publish_status = "blocked"
            suggestion.publish_message = reason
            suggestion.publish_block_reason = reason
            suggestion.publish_completed_at = blocked_at
            suggestion.last_transition_at = blocked_at
            status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
            status_log = update_status_stage(
                status_log,
                "publish_attempted",
                status="failed",
                message=reason,
                actor="system",
                occurred_at=blocked_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_result",
                status="blocked",
                message=reason,
                actor="system",
                occurred_at=blocked_at,
            )
            apply_status_log(suggestion, status_log)
            db.add(SystemLog(level="warning", module="publish_suggestion", message=reason, app_id=app_id))
            _safe_commit()
            return {"status": "blocked", "reason": reason}

        similar_live_reason = recent_live_publish_block_reason(suggestion, db) if not dry_run else None
        if similar_live_reason:
            blocked_at = utcnow_naive()
            suggestion.publish_status = "blocked"
            suggestion.publish_message = similar_live_reason
            suggestion.publish_block_reason = similar_live_reason
            suggestion.publish_completed_at = blocked_at
            suggestion.last_transition_at = blocked_at
            status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
            status_log = update_status_stage(
                status_log,
                "publish_attempted",
                status="failed",
                message=similar_live_reason,
                actor="system",
                occurred_at=blocked_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_result",
                status="blocked",
                message=similar_live_reason,
                actor="system",
                occurred_at=blocked_at,
            )
            apply_status_log(suggestion, status_log)
            db.add(SystemLog(level="warning", module="publish_suggestion", message=similar_live_reason, app_id=app_id))
            _safe_commit()
            return {"status": "blocked", "reason": similar_live_reason}

        result = execution.publish(
            suggestion=suggestion,
            app=app,
            credential_json=credential_json,
            dry_run=dry_run,
            db=db,
        )
        completed_at = utcnow_naive()
        suggestion.last_transition_at = completed_at
        status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
        if result.get("success"):
            outcome_message = result.get("message") or (
                "Dry run completed."
                if result.get("dry_run")
                else "Published on Google Play."
            )
            status_log = update_status_stage(
                status_log,
                "waiting_safe_window",
                status="completed",
                message="Safe publish window available.",
                actor="system",
                occurred_at=suggestion.publish_started_at or completed_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_attempted",
                status="completed",
                message=outcome_message,
                actor="system",
                occurred_at=completed_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_result",
                status="completed",
                message=(
                    "Published on Google Play."
                    if suggestion.published_live
                    else "Dry run publish simulated. Nothing was sent to Google."
                ),
                actor="system",
                occurred_at=completed_at,
            )
        else:
            outcome_message = result.get("message", "Publish failed")
            terminal_status = "blocked" if suggestion.publish_status == "blocked" or result.get("status") == "blocked" else "failed"
            status_log = update_status_stage(
                status_log,
                "publish_attempted",
                status="blocked" if terminal_status == "blocked" else "failed",
                message=outcome_message,
                actor="system",
                occurred_at=completed_at,
            )
            status_log = update_status_stage(
                status_log,
                "publish_result",
                status="blocked" if terminal_status == "blocked" else "failed",
                message=outcome_message,
                actor="system",
                occurred_at=completed_at,
            )
        apply_status_log(suggestion, status_log)
        _safe_commit()

        db.add(
            SystemLog(
                level="info" if result.get("success") else "warning",
                module="publish_suggestion",
                message=f"Suggestion {suggestion_id}: {result.get('message', 'publish attempt finished')}",
                app_id=app_id,
            )
        )
        _safe_commit()
        logger.info("publish_suggestion task finished for suggestion %s: %s", suggestion_id, result)
        return result
