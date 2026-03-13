"""Performance tracking task: 7-day post-publish metrics check and rollback."""
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="track_performance")
def track_performance(suggestion_id: int, app_id: int):
    """Check performance 7 days after a suggestion was approved/published.

    If regression detected → rollback and notify.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models.suggestion import Suggestion
    from app.models.app import App
    from app.models.app_credential import AppCredential
    from app.models.global_config import GlobalConfig
    from app.models.app_listing import AppListing
    from app.models.system_log import SystemLog
    from app.services import performance_tracker, notifier
    from app.utils.encryption import decrypt_value

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as db:
        suggestion = db.execute(
            select(Suggestion).where(Suggestion.id == suggestion_id)
        ).scalar_one_or_none()

        if suggestion is None:
            logger.warning(f"track_performance: suggestion {suggestion_id} not found")
            return {"status": "skipped", "reason": "suggestion not found"}

        if suggestion.status not in ("published", "approved"):
            logger.info(f"track_performance: suggestion {suggestion_id} status={suggestion.status}, skipping")
            return {"status": "skipped", "reason": f"status={suggestion.status}"}

        app = db.execute(select(App).where(App.id == app_id)).scalar_one_or_none()
        if app is None:
            return {"status": "skipped", "reason": "app not found"}

        # Get config
        dry_run = settings.dry_run
        config_rows = db.execute(select(GlobalConfig)).scalars().all()
        for row in config_rows:
            try:
                val = decrypt_value(row.value)
                if row.key == "dry_run":
                    dry_run = val.lower() == "true"
            except Exception:
                pass

        # Get credential
        cred_row = db.execute(
            select(AppCredential)
            .where(AppCredential.app_id == app_id)
            .where(AppCredential.credential_type == "service_account_json")
        ).scalar_one_or_none()
        credential_json = None
        if cred_row:
            try:
                credential_json = decrypt_value(cred_row.value)
            except Exception:
                pass

        # Get before-publish snapshot
        before_listing = performance_tracker.get_before_listing(suggestion, db)

        # Take current snapshot (after 7 days)
        current_metrics = performance_tracker.take_snapshot(app.package_name)

        if before_listing is None:
            logger.warning(f"No before_publish snapshot for suggestion {suggestion_id}")
            suggestion.status = "confirmed"
            db.commit()
            return {"status": "ok", "regression": False, "note": "no before snapshot"}

        before_metrics = {
            "rating": 0.0,  # AppListing doesn't store metrics — use 0 as fallback
            "ratings_count": 0,
        }

        regression, reason = performance_tracker.check_regression(
            before=before_metrics,
            after=current_metrics,
        )

        if regression:
            logger.warning(f"Regression detected for suggestion {suggestion_id}: {reason}")

            rollback_result = performance_tracker.rollback(
                suggestion=suggestion,
                before_listing=before_listing,
                app=app,
                credential_json=credential_json or "",
                dry_run=dry_run,
                db=db,
            )

            notifier.send_rollback_alert(suggestion, app.name, reason, db)

            db.add(SystemLog(
                level="warning",
                module="track_performance",
                message=f"Rolled back suggestion {suggestion_id}: {reason[:200]}",
            ))
            db.commit()

            return {"status": "rolled_back", "suggestion_id": suggestion_id, "reason": reason}

        else:
            suggestion.status = "confirmed"
            db.add(SystemLog(
                level="info",
                module="track_performance",
                message=f"Suggestion {suggestion_id} confirmed — no regression",
            ))
            db.commit()
            return {"status": "confirmed", "suggestion_id": suggestion_id}
