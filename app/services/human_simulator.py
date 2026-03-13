"""Human simulator: random delays to mimic human publishing behavior."""
import asyncio
import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Publishing time window: 9 AM - 10 PM UTC
PUBLISH_WINDOW_START = 9
PUBLISH_WINDOW_END = 22


def is_publish_window() -> bool:
    """Check if current UTC time is within the publishing window (9 AM - 10 PM)."""
    now = datetime.now(timezone.utc)
    return PUBLISH_WINDOW_START <= now.hour < PUBLISH_WINDOW_END


async def pipeline_delay(dry_run: bool = False) -> None:
    """Wait a random 5-20 minute delay before running pipeline steps.

    In dry_run mode: no delay (for fast testing).
    """
    if dry_run:
        logger.debug("pipeline_delay: skipped (dry_run=True)")
        return

    delay_seconds = random.randint(5 * 60, 20 * 60)  # 5-20 minutes
    logger.info(f"Human simulation: pipeline delay {delay_seconds // 60} minutes")
    await asyncio.sleep(delay_seconds)


def pipeline_delay_sync(dry_run: bool = False) -> None:
    """Sync version of pipeline_delay for use in Celery tasks."""
    import time

    if dry_run:
        return

    delay_seconds = random.randint(5 * 60, 20 * 60)
    logger.info(f"Human simulation: pipeline delay {delay_seconds // 60} minutes")
    time.sleep(delay_seconds)


async def publish_delay(dry_run: bool = False) -> None:
    """Wait a random 45 min - 3 hour delay before publishing.

    In dry_run mode: no delay.
    """
    if dry_run:
        logger.debug("publish_delay: skipped (dry_run=True)")
        return

    delay_seconds = random.randint(45 * 60, 3 * 60 * 60)  # 45 min - 3 hours
    logger.info(f"Human simulation: publish delay {delay_seconds // 60} minutes")
    await asyncio.sleep(delay_seconds)


def publish_delay_sync(dry_run: bool = False) -> None:
    """Sync version of publish_delay for Celery tasks."""
    import time

    if dry_run:
        return

    delay_seconds = random.randint(45 * 60, 3 * 60 * 60)
    logger.info(f"Human simulation: publish delay {delay_seconds // 60} minutes")
    time.sleep(delay_seconds)
