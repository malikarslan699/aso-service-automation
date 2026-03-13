"""Performance tracker: metrics comparison and rollback logic."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def take_snapshot(package_name: str) -> dict:
    """Fetch current app performance metrics from Google Play.

    Returns:
        dict with rating, ratings_count, installs, date
    """
    from app.services.data_fetcher import fetch_listing

    listing = fetch_listing(package_name)
    return {
        "rating": listing.get("rating", 0.0),
        "ratings_count": listing.get("ratings_count", 0),
        "reviews_count": listing.get("reviews_count", 0),
        "installs": listing.get("installs", "0"),
        "date": datetime.now(timezone.utc).isoformat(),
    }


def check_regression(
    before: dict,
    after: dict,
    rating_threshold: float = 0.05,
) -> tuple[bool, str]:
    """Compare before/after metrics to detect performance regression.

    Args:
        before: metrics dict before publish
        after: metrics dict after publish (7 days later)
        rating_threshold: minimum rating drop fraction to flag (default 5%)

    Returns:
        (regression_detected: bool, reason: str)
    """
    before_rating = float(before.get("rating", 0.0))
    after_rating = float(after.get("rating", 0.0))

    if before_rating > 0 and after_rating > 0:
        drop_fraction = (before_rating - after_rating) / before_rating
        if drop_fraction >= rating_threshold:
            return True, (
                f"Rating dropped from {before_rating:.2f} to {after_rating:.2f} "
                f"({drop_fraction * 100:.1f}% drop — threshold {rating_threshold * 100:.0f}%)"
            )

    return False, "No significant regression detected"


def rollback(
    suggestion,
    before_listing,
    app,
    credential_json: str,
    dry_run: bool,
    db,
) -> dict:
    """Roll back a published suggestion by restoring the before-publish listing.

    Args:
        suggestion: Suggestion ORM instance (must be status="published")
        before_listing: AppListing ORM instance with snapshot_type="before_publish"
        app: App ORM instance
        credential_json: service account JSON
        dry_run: if True, simulate only
        db: SQLAlchemy session

    Returns:
        dict with success, message
    """
    from app.services.data_fetcher import publish_listing
    from datetime import datetime, timezone

    field = suggestion.field_name

    if dry_run:
        logger.info(f"[DRY RUN] Would rollback {field} for app {app.id}")
        suggestion.status = "rolled_back"
        db.commit()
        return {"success": True, "dry_run": True, "message": "Dry run rollback"}

    kwargs = {
        "package_name": app.package_name,
        "credential_json": credential_json,
        "dry_run": False,
    }
    if field == "title":
        kwargs["title"] = before_listing.title
    elif field == "short_description":
        kwargs["short_description"] = before_listing.short_description
    elif field == "long_description":
        kwargs["long_description"] = before_listing.long_description
    else:
        logger.warning(f"Rollback not supported for field: {field}")
        return {"success": False, "message": f"Rollback not supported for {field}"}

    result = publish_listing(**kwargs)

    if result.get("success"):
        suggestion.status = "rolled_back"
        db.commit()
        logger.info(f"Rolled back suggestion {suggestion.id} for app {app.id}")
    else:
        logger.error(f"Rollback failed for suggestion {suggestion.id}: {result.get('message')}")

    return result


def get_before_listing(suggestion, db):
    """Find the AppListing before_publish snapshot for a suggestion's app."""
    from sqlalchemy import select
    from app.models.app_listing import AppListing

    return db.execute(
        select(AppListing)
        .where(AppListing.app_id == suggestion.app_id)
        .where(AppListing.snapshot_type == "before_publish")
        .order_by(AppListing.id.desc())
    ).scalar_one_or_none()
