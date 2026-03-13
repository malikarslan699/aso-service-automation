"""Shared duplicate and publish guard helpers for long-term listing safety."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher


LISTING_FIELD_COOLDOWNS = {
    "title": 30,
    "short_description": 14,
    "long_description": 14,
}

NEAR_DUPLICATE_THRESHOLD = 0.88


def normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip().casefold()


def parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def similarity_score(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0

    char_ratio = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    left_tokens = {token for token in normalized_left.split() if len(token) >= 3}
    right_tokens = {token for token in normalized_right.split() if len(token) >= 3}
    token_ratio = 0.0
    if left_tokens and right_tokens:
        token_ratio = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    return max(char_ratio, token_ratio)


def is_near_duplicate(left: str, right: str, threshold: float = NEAR_DUPLICATE_THRESHOLD) -> bool:
    return similarity_score(left, right) >= threshold


def should_skip_candidate(candidate: dict, existing_suggestions: list[dict], now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    field_name = candidate.get("field_name", "")
    suggestion_type = candidate.get("suggestion_type", "")
    normalized_new = normalize_text(candidate.get("new_value", ""))
    normalized_old = normalize_text(candidate.get("old_value", ""))

    if not normalized_new:
        return True, "empty new value"
    if normalized_new == normalized_old:
        return True, "matches current live value"

    for existing in existing_suggestions:
        if existing.get("field_name") != field_name:
            continue
        existing_status = existing.get("status")
        if existing_status not in {"pending", "approved", "published"}:
            continue

        existing_value = existing.get("new_value", "")
        if normalize_text(existing_value) == normalized_new:
            return True, "exact duplicate already exists"

        if suggestion_type != "listing":
            continue

        if existing_status in {"pending", "approved"} and is_near_duplicate(existing_value, candidate.get("new_value", "")):
            return True, "near-duplicate item is already awaiting review/publish"

        cooldown_days = LISTING_FIELD_COOLDOWNS.get(field_name)
        existing_published_at = parse_datetime(existing.get("published_at")) or parse_datetime(existing.get("created_at"))
        if (
            existing_status == "published"
            and cooldown_days
            and existing_published_at
            and existing_published_at >= now - timedelta(days=cooldown_days)
            and is_near_duplicate(existing_value, candidate.get("new_value", ""))
        ):
            return True, f"similar {field_name} was already published recently"

    return False, ""


def recent_live_publish_block_reason(suggestion, db, now: datetime | None = None) -> str | None:
    from sqlalchemy import select
    from app.models.suggestion import Suggestion

    if getattr(suggestion, "suggestion_type", "") != "listing":
        return None

    cooldown_days = LISTING_FIELD_COOLDOWNS.get(getattr(suggestion, "field_name", ""))
    if not cooldown_days:
        return None

    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=cooldown_days)
    recent_live_items = db.execute(
        select(Suggestion)
        .where(Suggestion.app_id == suggestion.app_id)
        .where(Suggestion.field_name == suggestion.field_name)
        .where(Suggestion.status == "published")
        .where(Suggestion.published_at >= cutoff)
        .where(Suggestion.id != suggestion.id)
        .order_by(Suggestion.published_at.desc())
    ).scalars().all()

    for recent in recent_live_items:
        if is_near_duplicate(recent.new_value, suggestion.new_value):
            published_at = recent.published_at.strftime("%Y-%m-%d") if recent.published_at else "recently"
            return (
                f"A very similar {suggestion.field_name.replace('_', ' ')} was already published on Google on "
                f"{published_at}. Approval was kept, but another live send was blocked."
            )

    return None
