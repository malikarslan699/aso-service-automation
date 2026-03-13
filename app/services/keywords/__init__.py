"""AI-Driven Keyword Discovery Engine.

Main entry point: run_discovery(app, db) -> dict

Pipeline:
1. Fetch competitor metadata (competitor_fetcher)
2. Extract keywords from competitors + Play Store suggestions (keyword_extractor)
3. Cluster keywords with Claude (keyword_clusterer)
4. Score and rank by opportunity (opportunity_scorer)
5. Detect trends vs last week (trend_detector)
6. Save to Keyword model in DB
"""
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_discovery(
    app_id: int,
    package_name: str,
    app_facts: list[dict],
    db: Session,
    anthropic_api_key: str = "",
    openai_api_key: str = "",
) -> dict:
    """Run the full keyword discovery pipeline for an app.

    Args:
        app_id: DB app ID
        package_name: e.g. "com.NetSafe.VPN"
        app_facts: list of {fact_key, fact_value}
        db: SQLAlchemy session
        anthropic_api_key: for Claude clustering

    Returns:
        dict with keywords, trends, opportunities, clusters
    """
    from app.services.keywords.competitor_fetcher import fetch_all_competitors
    from app.services.keywords.keyword_extractor import (
        extract_from_competitors,
        get_play_store_suggestions,
    )
    from app.services.keywords.keyword_clusterer import cluster_keywords
    from app.services.keywords.opportunity_scorer import rank_keywords, save_keywords_to_db
    from app.services.keywords.trend_detector import detect_trends
    from app.models.keyword import Keyword
    from sqlalchemy import select

    logger.info(f"Starting keyword discovery for app_id={app_id}, package={package_name}")

    # Step 1: Fetch competitors
    category = "vpn" if "vpn" in package_name.lower() else "vpn"
    competitors = fetch_all_competitors(category=category)

    # Step 2: Extract keywords
    keyword_frequencies = extract_from_competitors(competitors)

    # Also get Play Store suggestions for seed keywords
    play_suggestions = []
    seed = package_name.split(".")[-1].lower()  # e.g. "vpn" from "com.NetSafe.VPN"
    play_suggestions.extend(get_play_store_suggestions(seed))

    # Step 3: Cluster with Claude
    all_keywords = list(keyword_frequencies.keys())
    cluster_result = cluster_keywords(
        keywords=all_keywords[:80],
        app_facts=app_facts,
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
    )
    clusters = cluster_result.get("clusters", [])

    # Step 4: Score and rank
    ranked = rank_keywords(
        keyword_frequencies=keyword_frequencies,
        app_facts=app_facts,
        play_suggestions=play_suggestions,
        top_n=50,
    )

    # Step 5: Detect trends (compare with previous week's DB data)
    previous_keywords = [
        {"keyword": kw.keyword, "opportunity_score": kw.opportunity_score}
        for kw in db.execute(
            select(Keyword)
            .where(Keyword.app_id == app_id)
            .where(Keyword.status == "active")
        ).scalars().all()
    ]
    trends = detect_trends(current_keywords=ranked, previous_keywords=previous_keywords)

    # Step 6: Save to DB
    saved_count = save_keywords_to_db(app_id=app_id, ranked_keywords=ranked, db=db)

    rising_trends = [t for t in trends if t["trend"] == "rising"]

    logger.info(
        f"Keyword discovery complete: {len(ranked)} ranked, {saved_count} new, "
        f"{len(rising_trends)} rising trends"
    )

    return {
        "keywords": ranked,
        "trends": trends,
        "clusters": clusters,
        "competitors_analyzed": len(competitors),
        "rising_trends": rising_trends,
        "play_suggestions_count": len(play_suggestions),
        "cluster_provider": cluster_result.get("provider_name"),
        "cluster_fallback_provider": cluster_result.get("fallback_provider_name"),
        "cluster_provider_status": cluster_result.get("provider_status"),
        "cluster_provider_error_class": cluster_result.get("provider_error_class"),
        "cluster_estimated_cost": cluster_result.get("estimated_cost", 0.0),
        "cluster_input_tokens": cluster_result.get("input_tokens", 0),
        "cluster_output_tokens": cluster_result.get("output_tokens", 0),
        "cluster_message": cluster_result.get("message"),
    }
