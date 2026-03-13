"""Execution service: publish suggestions with rate limiting."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _is_true(val, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes"}


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
    from app.services.runtime_config import as_int, load_runtime_config

    config = load_runtime_config(db)
    publish_mode = (config.get("publish_mode") or "live").strip().lower()
    if publish_mode not in {"soft", "live"}:
        publish_mode = "live"

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

    # --- Human sim: publish window + random delay ---
    human_sim_enabled = _is_true(config.get("human_sim_enabled"), False)
    if not dry_run and human_sim_enabled and publish_mode != "soft":
        from app.services import human_simulator
        if not human_simulator.is_publish_window():
            app_name = getattr(app, "name", str(app.id))
            suggestion.publish_status = "pending_window"
            suggestion.publish_message = "Outside safe publish window (9AM–10PM UTC). Will publish in next window."
            suggestion.last_transition_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
            from app.services import notifier
            notifier.send_publish_blocked(app_name, "Outside publish window (9AM–10PM UTC). Queued for next window.", db)
            return {
                "success": False,
                "dry_run": False,
                "status": "pending_window",
                "message": suggestion.publish_message,
            }
        pub_min = as_int(config.get("publish_delay_min_minutes"), 45)
        pub_max = as_int(config.get("publish_delay_max_minutes"), 180)
        delay_s = human_simulator.compute_publish_delay_seconds(dry_run=dry_run, enabled=human_sim_enabled, min_minutes=pub_min, max_minutes=pub_max)
        if delay_s > 0:
            logger.info("Human sim: publish delay %s minutes for app %s", delay_s // 60, app.id)
            human_simulator.publish_delay_sync(dry_run=dry_run, enabled=human_sim_enabled, delay_seconds=delay_s)

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
    suggestion.google_play_edit_id = None

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
            "commit_edit": publish_mode != "soft",
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
            suggestion.google_play_edit_id = None
        elif result.get("status") == "soft_published":
            suggestion.publish_status = "soft_published"
            suggestion.status = "approved"
            suggestion.published_at = None
            suggestion.published_live = False
            suggestion.is_dry_run_result = False
            suggestion.google_play_edit_id = result.get("edit_id")
        else:
            suggestion.publish_status = "published"
            suggestion.status = "published"
            suggestion.published_at = completed_at
            suggestion.google_play_edit_id = None

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

        # Telegram notifications
        from app.services import notifier
        app_name = getattr(app, "name", str(app.id))
        if result.get("dry_run"):
            pass  # dry run — no notification needed
        elif result.get("status") == "soft_published":
            notifier.send_soft_publish_notification(suggestion, app_name, db)
        else:
            notifier.send_publish_confirmation(suggestion, app_name, dry_run=False, db=db)
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

        from app.services import notifier
        app_name = getattr(app, "name", str(app.id))
        notifier.send_publish_blocked(app_name, result.get("message", "Publish failed"), db)

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
    from app.services.runtime_config import load_runtime_config

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

    config = load_runtime_config(db)
    publish_mode = (config.get("publish_mode") or "live").strip().lower()
    if publish_mode not in {"soft", "live"}:
        publish_mode = "live"

    result = data_fetcher.publish_listing(
        package_name=app.package_name,
        credential_json=credential_json or "",
        title=title,
        short_description=short_description,
        long_description=long_description,
        dry_run=dry_run,
        commit_edit=publish_mode != "soft",
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
