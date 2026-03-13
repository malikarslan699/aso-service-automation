"""Hourly task: retry suggestions that were blocked due to outside publish window."""
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="retry_publish_window")
def retry_publish_window_task():
    """Re-queue suggestions with publish_status='pending_window' if now inside the publish window."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.app import App
    from app.models.suggestion import Suggestion
    from app.services.human_simulator import is_publish_window
    from app.services.runtime_config import is_true, load_runtime_config

    if not is_publish_window():
        logger.debug("retry_publish_window: outside window, skipping")
        return {"status": "skipped", "reason": "outside_publish_window"}

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    queued = 0

    with Session(engine) as db:
        config = load_runtime_config(db)
        human_sim_enabled = is_true(config.get("human_sim_enabled"), True)
        dry_run = is_true(config.get("dry_run"), settings.dry_run)

        if not human_sim_enabled or dry_run:
            return {"status": "skipped", "reason": "human_sim_disabled_or_dry_run"}

        rows = db.execute(
            select(Suggestion)
            .where(Suggestion.publish_status == "pending_window")
            .where(Suggestion.status == "approved")
        ).scalars().all()

        for suggestion in rows:
            app = db.execute(select(App).where(App.id == suggestion.app_id)).scalar_one_or_none()
            if app is None or app.status != "active":
                continue

            suggestion.publish_status = "ready"
            suggestion.publish_message = "Publish window opened — re-queued for publish."
            db.commit()

            celery_app.send_task(
                "publish_suggestion",
                kwargs={"suggestion_id": suggestion.id, "app_id": suggestion.app_id},
            )
            queued += 1
            logger.info("retry_publish_window: re-queued suggestion %s for app %s", suggestion.id, suggestion.app_id)

    return {"status": "ok", "requeued": queued}
