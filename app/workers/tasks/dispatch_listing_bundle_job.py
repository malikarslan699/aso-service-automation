"""Celery task for paced listing bundle dispatch."""
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="dispatch_listing_bundle_job")
def dispatch_listing_bundle_job_task(job_id: int):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.services.listing_publish_queue import dispatch_listing_bundle_job

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as db:
        result = dispatch_listing_bundle_job(db, job_id=job_id)
        logger.info("dispatch_listing_bundle_job finished for job %s: %s", job_id, result)
        return result
