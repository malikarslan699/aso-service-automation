"""Dispatch task: called by Celery Beat daily.
Uses dynamic_scheduler to decide if today's pipeline should run and when."""
from datetime import datetime, timezone, timedelta
from app.workers.celery_app import celery_app
from app.workers.dynamic_scheduler import generate_daily_schedule


@celery_app.task(name="dispatch_pipeline")
def dispatch_pipeline():
    """Query all active apps and schedule daily_pipeline for each one.

    Uses generate_daily_schedule() to:
    - Possibly skip today (2 random skip days/week)
    - Pick a random hour (9-22) different from yesterday
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.config import get_settings
    from app.models.app import App
    from app.models.pipeline_run import PipelineRun

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    with Session(engine) as db:
        apps = db.execute(select(App).where(App.status == "active")).scalars().all()

        for app in apps:
            # Get last pipeline hour to avoid repeating same hour
            last_run = db.execute(
                select(PipelineRun)
                .where(PipelineRun.app_id == app.id)
                .order_by(PipelineRun.id.desc())
                .limit(1)
            ).scalar_one_or_none()

            last_hour = -1
            if last_run and last_run.created_at:
                last_hour = last_run.created_at.hour

            schedule = generate_daily_schedule(last_hour=last_hour)

            if schedule["should_skip"]:
                continue

            # Calculate ETA for today at the scheduled hour/minute
            now = datetime.now(timezone.utc)
            eta = now.replace(hour=schedule["hour"], minute=schedule["minute"], second=0, microsecond=0)
            if eta < now:
                eta += timedelta(days=1)

            celery_app.send_task("daily_pipeline", args=[app.id], eta=eta)

    return {"dispatched": len(apps), "timestamp": datetime.now(timezone.utc).isoformat()}
