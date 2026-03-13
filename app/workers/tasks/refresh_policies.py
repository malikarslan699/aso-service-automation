"""Weekly policy refresh task."""
import logging
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="refresh_policies")
def refresh_policies():
    """Refresh Google Play policy cache in DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.services.policy_engine import update_policy_cache
    from app.models.system_log import SystemLog

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as db:
        success = update_policy_cache(db)

        db.add(SystemLog(
            level="info" if success else "error",
            module="refresh_policies",
            message="Policy cache refresh " + ("succeeded" if success else "failed"),
        ))
        db.commit()

    logger.info(f"refresh_policies: {'ok' if success else 'failed'}")
    return {"status": "ok" if success else "failed"}
