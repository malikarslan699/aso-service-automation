"""Execution service: publish suggestions with rate limiting."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _count_suggestion_publishes(app_id: int, db, *, since: datetime, suggestion_type: str) -> int:
    from sqlalchemy import func, select

    from app.models.suggestion import Suggestion

    return (
        db.execute(
            select(func.count())
            .select_from(Suggestion)
            .where(Suggestion.app_id == app_id)
            .where(Suggestion.suggestion_type == suggestion_type)
            .where(Suggestion.status == "published")
            .where(Suggestion.published_at >= since)
        ).scalar()
        or 0
    )


def _count_listing_bundle_executions(app_id: int, db, *, since: datetime) -> int:
    from sqlalchemy import func, select

    from app.models.listing_publish_job import ListingPublishJob

    return (
        db.execute(
            select(func.count())
            .select_from(ListingPublishJob)
            .where(ListingPublishJob.app_id == app_id)
            .where(ListingPublishJob.status.in_(("published", "dry_run_only")))
            .where(ListingPublishJob.executed_at >= since)
        ).scalar()
        or 0
    )


def can_publish(app_id: int, db, publish_kind: str = "listing", now: datetime | None = None) -> tuple[bool, str]:
    """Check if publishing is allowed based on rate limits.

    publish_kind:
      - listing: listing bundle publish limits
      - review_reply: review reply publish limits
    """
    from app.services.runtime_config import as_int, load_runtime_config

    config = load_runtime_config(db)
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())

    if publish_kind == "review_reply":
        max_per_day = as_int(config.get("review_reply_max_per_day"), 25)
        max_per_week = as_int(config.get("review_reply_max_per_week"), 120)

        today_count = _count_suggestion_publishes(
            app_id,
            db,
            since=day_start,
            suggestion_type="review_reply",
        )
        if today_count >= max_per_day:
            return False, f"Daily review-reply publish limit reached ({today_count}/{max_per_day})"

        week_count = _count_suggestion_publishes(
            app_id,
            db,
            since=week_start,
            suggestion_type="review_reply",
        )
        if week_count >= max_per_week:
            return False, f"Weekly review-reply publish limit reached ({week_count}/{max_per_week})"

        return True, "OK"

    max_per_day = as_int(config.get("listing_publish_max_per_day"), as_int(config.get("max_publish_per_day"), 1))
    max_per_week = as_int(config.get("listing_publish_max_per_week"), as_int(config.get("max_publish_per_week"), 5))

    today_count = _count_listing_bundle_executions(app_id, db, since=day_start)
    if today_count >= max_per_day:
        return False, f"Daily listing publish limit reached ({today_count}/{max_per_day})"

    week_count = _count_listing_bundle_executions(app_id, db, since=week_start)
    if week_count >= max_per_week:
        return False, f"Weekly listing publish limit reached ({week_count}/{max_per_week})"

    return True, "OK"


def publish(
    suggestion,
    app,
    credential_json: Optional[str],
    dry_run: bool,
    db,
) -> dict:
    """Publish an approved suggestion to Google Play."""
    from app.models.app_listing import AppListing
    from app.services import data_fetcher

    if credential_json is None and not dry_run:
        logger.warning(f"Missing Google Play credential for app {app.id} while live publish was requested")
        suggestion.publish_status = "blocked"
        suggestion.publish_message = "[missing_google_credential] Missing Google Play credential. Live publish could not start."
        suggestion.publish_block_reason = suggestion.publish_message
        suggestion.publish_completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        suggestion.last_transition_at = suggestion.publish_completed_at
        db.commit()
        return {
            "success": False,
            "dry_run": False,
            "status": "blocked",
            "error_code": "missing_google_credential",
            "message": suggestion.publish_message,
        }

    if credential_json is None and dry_run:
        dry_run = True
        logger.warning(f"No credential for app {app.id} - forcing dry_run mode")

    current = data_fetcher.fetch_listing(app.package_name)
    before_snapshot = AppListing(
        app_id=app.id,
        title=current.get("title", ""),
        short_description=current.get("short_description", ""),
        long_description=current.get("long_description", ""),
        snapshot_type="before_publish",
    )
    db.add(before_snapshot)
    db.flush()

    field = suggestion.field_name
    result = {}

    if suggestion.suggestion_type == "review_reply":
        extra = {}
        try:
            import json
            extra = json.loads(getattr(suggestion, "extra_data", "{}") or "{}")
        except Exception:
            pass
        review_id = extra.get("review_id", "")
        result = data_fetcher.reply_to_review(
            package_name=app.package_name,
            review_id=review_id,
            reply_text=suggestion.new_value,
            credential_json=credential_json or "",
            dry_run=dry_run,
        )
    else:
        kwargs = {
            "package_name": app.package_name,
            "credential_json": credential_json or "",
            "dry_run": dry_run,
        }
        if field == "title":
            kwargs["title"] = suggestion.new_value
        elif field == "short_description":
            kwargs["short_description"] = suggestion.new_value
        elif field == "long_description":
            kwargs["long_description"] = suggestion.new_value
        result = data_fetcher.publish_listing(**kwargs)

    if result.get("success"):
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        suggestion.publish_completed_at = completed_at
        suggestion.last_transition_at = completed_at
        suggestion.publish_message = result.get("message", "Publish finished")
        suggestion.publish_block_reason = None
        suggestion.is_dry_run_result = bool(result.get("dry_run"))
        suggestion.published_live = not bool(result.get("dry_run"))

        if result.get("dry_run"):
            suggestion.publish_status = "dry_run_only"
            suggestion.status = "approved"
            suggestion.published_at = None
        else:
            suggestion.publish_status = "published"
            suggestion.status = "published"
            suggestion.published_at = completed_at

        after_listing = data_fetcher.fetch_listing(app.package_name)
        after_snapshot = AppListing(
            app_id=app.id,
            title=after_listing.get("title", ""),
            short_description=after_listing.get("short_description", ""),
            long_description=after_listing.get("long_description", ""),
            snapshot_type="after_publish",
        )
        db.add(after_snapshot)

        db.commit()
        logger.info(f"Published suggestion {suggestion.id} for app {app.id} (dry_run={dry_run})")
    else:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        publish_status = "blocked" if result.get("status") == "blocked" else "failed"
        suggestion.publish_status = publish_status
        suggestion.publish_completed_at = completed_at
        suggestion.last_transition_at = completed_at
        suggestion.publish_message = result.get("message", "Publish failed")
        suggestion.publish_block_reason = suggestion.publish_message
        logger.error(f"Publish failed for suggestion {suggestion.id}: {result.get('message')}")
        db.commit()

    return result


def publish_listing_bundle(
    *,
    app,
    credential_json: Optional[str],
    dry_run: bool,
    db,
    title: Optional[str] = None,
    short_description: Optional[str] = None,
    long_description: Optional[str] = None,
) -> dict:
    """Publish merged listing fields in one Google Play edit."""
    from app.models.app_listing import AppListing
    from app.services import data_fetcher

    if not title and not short_description and not long_description:
        return {
            "success": False,
            "dry_run": dry_run,
            "status": "blocked",
            "error_code": "missing_listing_payload",
            "message": "[missing_listing_payload] No listing fields in bundle payload",
        }

    if credential_json is None and not dry_run:
        logger.warning("Missing Google Play credential for app %s while live listing bundle was requested", app.id)
        return {
            "success": False,
            "dry_run": False,
            "status": "blocked",
            "error_code": "missing_google_credential",
            "message": "[missing_google_credential] Missing Google Play credential. Live listing publish could not start.",
        }

    if credential_json is None and dry_run:
        dry_run = True

    current = data_fetcher.fetch_listing(app.package_name)
    before_snapshot = AppListing(
        app_id=app.id,
        title=current.get("title", ""),
        short_description=current.get("short_description", ""),
        long_description=current.get("long_description", ""),
        snapshot_type="before_publish",
    )
    db.add(before_snapshot)
    db.flush()

    result = data_fetcher.publish_listing(
        package_name=app.package_name,
        credential_json=credential_json or "",
        title=title,
        short_description=short_description,
        long_description=long_description,
        dry_run=dry_run,
    )

    if result.get("success"):
        after_listing = data_fetcher.fetch_listing(app.package_name)
        after_snapshot = AppListing(
            app_id=app.id,
            title=after_listing.get("title", ""),
            short_description=after_listing.get("short_description", ""),
            long_description=after_listing.get("long_description", ""),
            snapshot_type="after_publish",
        )
        db.add(after_snapshot)

    return result
