"""Keyword opportunity scoring and ranking."""
import json
import logging

logger = logging.getLogger(__name__)


def score_keyword(
    keyword: str,
    competitor_frequency: int,
    total_competitors: int,
    in_app_facts: bool = False,
    in_play_suggestions: bool = False,
) -> float:
    """Calculate opportunity score for a keyword.

    Formula: base_score * relevance_boost
    - base_score = frequency / total_competitors (0.0 - 1.0)
    - relevance_boost: +50% if in app_facts, +20% if in Play suggestions

    Args:
        keyword: keyword string
        competitor_frequency: how many competitors use this keyword
        total_competitors: total number of competitors analyzed
        in_app_facts: True if keyword is supported by our app facts
        in_play_suggestions: True if keyword appears in Play Store suggestions

    Returns:
        float opportunity score (0.0 - 1.0+, capped at 1.0)
    """
    if total_competitors == 0:
        return 0.0

    base_score = competitor_frequency / total_competitors
    boost = 1.0
    if in_app_facts:
        boost += 0.5
    if in_play_suggestions:
        boost += 0.2

    return min(base_score * boost, 1.0)


def rank_keywords(
    keyword_frequencies: dict[str, int],
    app_facts: list[dict],
    play_suggestions: list[str],
    top_n: int = 50,
) -> list[dict]:
    """Score and rank all keywords by opportunity.

    Args:
        keyword_frequencies: {keyword: frequency_count} from competitor analysis
        app_facts: list of {fact_key, fact_value} dicts
        play_suggestions: list of keywords from Play Store suggestions
        top_n: number of top keywords to return

    Returns:
        list of ranked keyword dicts sorted by opportunity_score descending:
        [{keyword, frequency, opportunity_score, sources, recommended}]
    """
    total_competitors = max(keyword_frequencies.values(), default=1)

    # Build fact keywords set for quick lookup
    fact_keywords = set()
    for fact in app_facts:
        fact_text = f"{fact.get('fact_key', '')} {fact.get('fact_value', '')}".lower()
        words = fact_text.split()
        fact_keywords.update(words)
        # Also add bigrams from facts
        for i in range(len(words) - 1):
            fact_keywords.add(f"{words[i]} {words[i+1]}")

    play_suggestions_lower = {s.lower() for s in play_suggestions}

    ranked = []
    for keyword, frequency in keyword_frequencies.items():
        kw_lower = keyword.lower()

        # Check if keyword is supported by app facts
        in_app_facts = any(
            fact_kw in kw_lower or kw_lower in fact_kw
            for fact_kw in fact_keywords
            if len(fact_kw) > 3
        )

        in_play_suggestions = kw_lower in play_suggestions_lower

        # Determine sources
        sources = ["competitor"]
        if in_play_suggestions:
            sources.append("play_suggest")

        opp_score = score_keyword(
            keyword=keyword,
            competitor_frequency=frequency,
            total_competitors=total_competitors,
            in_app_facts=in_app_facts,
            in_play_suggestions=in_play_suggestions,
        )

        ranked.append({
            "keyword": keyword,
            "frequency": frequency,
            "opportunity_score": round(opp_score, 4),
            "sources": sources,
            "recommended": opp_score >= 0.4 and in_app_facts,
            "extra_data": json.dumps({
                "in_app_facts": in_app_facts,
                "in_play_suggestions": in_play_suggestions,
            }),
        })

    ranked.sort(key=lambda x: x["opportunity_score"], reverse=True)
    return ranked[:top_n]


def save_keywords_to_db(
    app_id: int,
    ranked_keywords: list[dict],
    db,
) -> int:
    """Upsert ranked keywords into the Keyword model.

    Returns number of keywords saved.
    """
    from sqlalchemy import select
    from app.models.keyword import Keyword

    saved = 0
    for kw_data in ranked_keywords:
        existing = db.execute(
            select(Keyword)
            .where(Keyword.app_id == app_id)
            .where(Keyword.keyword == kw_data["keyword"])
        ).scalar_one_or_none()

        sources_str = ",".join(kw_data["sources"])

        if existing:
            existing.opportunity_score = kw_data["opportunity_score"]
            existing.volume_signal = kw_data["frequency"] / 100.0
            existing.source = sources_str
            existing.extra_data = kw_data["extra_data"]
        else:
            db.add(Keyword(
                app_id=app_id,
                keyword=kw_data["keyword"],
                opportunity_score=kw_data["opportunity_score"],
                volume_signal=kw_data["frequency"] / 100.0,
                source=sources_str,
                extra_data=kw_data["extra_data"],
                status="active",
            ))
            saved += 1

    db.commit()
    logger.info(f"Saved {saved} new keywords for app {app_id}")
    return saved
