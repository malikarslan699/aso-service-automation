from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aso_service",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.daily_pipeline",
        "app.workers.tasks.dispatch_pipeline",
        "app.workers.tasks.publish_suggestion",
        "app.workers.tasks.dispatch_listing_bundle_job",
        "app.workers.tasks.refresh_policies",
        "app.workers.tasks.track_performance",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        # Dispatch daily pipeline at 8:55 AM UTC.
        # The dispatch task uses dynamic_scheduler to decide actual run time per app.
        "dispatch-daily-pipeline": {
            "task": "dispatch_pipeline",
            "schedule": crontab(hour=8, minute=55),
        },
        # Refresh Google Play policies every Monday at 2 AM UTC
        "refresh-policies-weekly": {
            "task": "refresh_policies",
            "schedule": crontab(day_of_week=1, hour=2, minute=0),
        },
    },
)
