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


def compute_pipeline_delay_seconds(dry_run: bool = False, enabled: bool = True, min_minutes: int = 5, max_minutes: int = 20) -> int:
    if dry_run or not enabled:
        return 0
    lo = max(1, min_minutes) * 60
    hi = max(lo, max_minutes * 60)
    return random.randint(lo, hi)


def compute_publish_delay_seconds(dry_run: bool = False, enabled: bool = True, min_minutes: int = 45, max_minutes: int = 180) -> int:
    if dry_run or not enabled:
        return 0
    lo = max(1, min_minutes) * 60
    hi = max(lo, max_minutes * 60)
    return random.randint(lo, hi)


async def pipeline_delay(dry_run: bool = False, enabled: bool = True, delay_seconds: int | None = None) -> int:
    """Wait a random 5-20 minute delay before running pipeline steps.

    In dry_run mode: no delay (for fast testing).
    """
    resolved_delay = compute_pipeline_delay_seconds(dry_run=dry_run, enabled=enabled) if delay_seconds is None else max(delay_seconds, 0)
    if resolved_delay <= 0:
        logger.debug("pipeline_delay: skipped (dry_run=%s, enabled=%s)", dry_run, enabled)
        return 0

    logger.info("Human simulation: pipeline delay %s minutes", resolved_delay // 60)
    await asyncio.sleep(resolved_delay)
    return resolved_delay


def pipeline_delay_sync(dry_run: bool = False, enabled: bool = True, delay_seconds: int | None = None) -> int:
    """Sync version of pipeline_delay for use in Celery tasks."""
    import time

    resolved_delay = compute_pipeline_delay_seconds(dry_run=dry_run, enabled=enabled) if delay_seconds is None else max(delay_seconds, 0)
    if resolved_delay <= 0:
        return 0

    logger.info("Human simulation: pipeline delay %s minutes", resolved_delay // 60)
    time.sleep(resolved_delay)
    return resolved_delay


async def publish_delay(dry_run: bool = False, enabled: bool = True, delay_seconds: int | None = None) -> int:
    """Wait a random 45 min - 3 hour delay before publishing.

    In dry_run mode: no delay.
    """
    resolved_delay = compute_publish_delay_seconds(dry_run=dry_run, enabled=enabled) if delay_seconds is None else max(delay_seconds, 0)
    if resolved_delay <= 0:
        logger.debug("publish_delay: skipped (dry_run=%s, enabled=%s)", dry_run, enabled)
        return 0

    logger.info("Human simulation: publish delay %s minutes", resolved_delay // 60)
    await asyncio.sleep(resolved_delay)
    return resolved_delay


def publish_delay_sync(dry_run: bool = False, enabled: bool = True, delay_seconds: int | None = None) -> int:
    """Sync version of publish_delay for Celery tasks."""
    import time

    resolved_delay = compute_publish_delay_seconds(dry_run=dry_run, enabled=enabled) if delay_seconds is None else max(delay_seconds, 0)
    if resolved_delay <= 0:
        return 0

    logger.info("Human simulation: publish delay %s minutes", resolved_delay // 60)
    time.sleep(resolved_delay)
    return resolved_delay
