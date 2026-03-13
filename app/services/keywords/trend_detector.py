"""Keyword trend detection: rising/falling keywords and competitor drops."""
import logging

logger = logging.getLogger(__name__)


def detect_trends(
    current_keywords: list[dict],
    previous_keywords: list[dict],
    change_threshold: float = 0.20,
) -> list[dict]:
    """Compare current vs previous keyword scores to detect trends.

    Args:
        current_keywords: current ranked keywords [{keyword, opportunity_score, ...}]
        previous_keywords: previous week's keywords
        change_threshold: minimum fractional change to flag (default 20%)

    Returns:
        list of trend dicts:
        [{keyword, trend: "rising"|"falling"|"new"|"stable", change_pct}]
    """
    prev_map = {kw["keyword"]: kw["opportunity_score"] for kw in previous_keywords}
    curr_map = {kw["keyword"]: kw["opportunity_score"] for kw in current_keywords}

    trends = []

    for keyword, curr_score in curr_map.items():
        if keyword not in prev_map:
            trends.append({
                "keyword": keyword,
                "trend": "new",
                "change_pct": 100.0,
                "current_score": curr_score,
                "previous_score": 0.0,
            })
            continue

        prev_score = prev_map[keyword]
        if prev_score == 0:
            change_pct = 100.0 if curr_score > 0 else 0.0
        else:
            change_pct = ((curr_score - prev_score) / prev_score) * 100

        if abs(change_pct) < change_threshold * 100:
            trend = "stable"
        elif change_pct > 0:
            trend = "rising"
        else:
            trend = "falling"

        if trend != "stable":
            trends.append({
                "keyword": keyword,
                "trend": trend,
                "change_pct": round(change_pct, 1),
                "current_score": curr_score,
                "previous_score": prev_score,
            })

    # Sort: rising first, then new, then falling
    order = {"rising": 0, "new": 1, "falling": 2}
    trends.sort(key=lambda x: (order.get(x["trend"], 3), -abs(x["change_pct"])))

    logger.info(f"Detected {len(trends)} keyword trends (threshold={change_threshold*100:.0f}%)")
    return trends


def check_competitor_drops(
    current_competitors: list[dict],
    previous_competitors: list[dict],
    drop_threshold: float = 0.1,
) -> list[dict]:
    """Detect competitors that have dropped in rating/installs → opportunity for us.

    Args:
        current_competitors: current competitor metadata
        previous_competitors: previous competitor metadata
        drop_threshold: minimum rating drop to flag (default 0.1 stars)

    Returns:
        list of opportunity dicts:
        [{competitor, package_name, opportunity: "rating_drop"|"no_data"}]
    """
    prev_map = {c["package_name"]: c for c in previous_competitors}
    opportunities = []

    for curr in current_competitors:
        pkg = curr.get("package_name", "")
        if pkg not in prev_map:
            continue

        prev = prev_map[pkg]
        curr_rating = curr.get("rating", 0.0)
        prev_rating = prev.get("rating", 0.0)

        if prev_rating > 0 and (prev_rating - curr_rating) >= drop_threshold:
            opportunities.append({
                "competitor": curr.get("title", pkg),
                "package_name": pkg,
                "opportunity": "competitor_weakened",
                "rating_drop": round(prev_rating - curr_rating, 2),
                "current_rating": curr_rating,
                "previous_rating": prev_rating,
            })

    logger.info(f"Found {len(opportunities)} competitor drop opportunities")
    return opportunities
