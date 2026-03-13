"""AI-powered keyword clustering with provider fallback."""
from __future__ import annotations

import logging

from app.services.ai_provider import (
    anthropic_complete,
    extract_json_array,
    openai_complete,
)

logger = logging.getLogger(__name__)


def cluster_keywords(
    keywords: list[str],
    app_facts: list[dict],
    anthropic_api_key: str,
    openai_api_key: str = "",
) -> dict:
    if not keywords:
        return _result(_fallback_clusters(keywords), provider_name=None, message="No keywords to cluster")

    if not anthropic_api_key and not openai_api_key:
        return _result(_fallback_clusters(keywords), provider_name=None, message="No AI provider configured for clustering")

    facts_text = "\n".join(f"- {fact['fact_key']}: {fact['fact_value']}" for fact in app_facts) or "No facts available"
    keywords_text = ", ".join(keywords[:80])
    prompt = f"""You are an ASO expert.

App facts:
{facts_text}

Keywords:
{keywords_text}

Return ONLY valid JSON array:
[
  {{
    "cluster_name": "security",
    "keywords": ["secure vpn"],
    "matches_our_app": true,
    "recommended": true
  }}
]
"""

    attempts = []
    if anthropic_api_key:
        attempts.append(anthropic_complete(prompt, 1500, anthropic_api_key))
    if openai_api_key:
        attempts.append(openai_complete(prompt, 1200, openai_api_key))

    first_failure = None
    for result in attempts:
        if result["ok"]:
            try:
                clusters = extract_json_array(result["text"])
            except Exception as exc:
                logger.warning("Keyword clustering JSON parse failed for %s: %s", result["provider"], exc)
                first_failure = first_failure or {
                    "provider": result["provider"],
                    "status": "provider_error",
                    "error_class": "provider_error",
                    "error_message": "Could not parse keyword clusters",
                }
                continue
            fallback_used = bool(anthropic_api_key) and result["provider"] == "openai"
            return {
                "clusters": clusters,
                "provider_name": result["provider"],
                "fallback_provider_name": "openai" if fallback_used else None,
                "provider_status": result["status"],
                "provider_error_class": None,
                "estimated_cost": result["estimated_cost"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "message": f"{result['provider'].title()} clustered keywords successfully.",
            }
        first_failure = first_failure or result
        logger.warning("Keyword clustering provider %s failed: %s", result["provider"], result["error_message"])

    return {
        "clusters": _fallback_clusters(keywords),
        "provider_name": first_failure["provider"] if first_failure else None,
        "fallback_provider_name": "openai" if anthropic_api_key and openai_api_key else None,
        "provider_status": first_failure["status"] if first_failure else "provider_error",
        "provider_error_class": first_failure["error_class"] if first_failure else "provider_error",
        "estimated_cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "message": (first_failure or {}).get("error_message", "Clustering fell back to rule-based mode."),
    }


def _result(clusters: list[dict], provider_name: str | None, message: str) -> dict:
    return {
        "clusters": clusters,
        "provider_name": provider_name,
        "fallback_provider_name": None,
        "provider_status": "provider_error" if provider_name is None else "inference_healthy",
        "provider_error_class": None,
        "estimated_cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "message": message,
    }


def _fallback_clusters(keywords: list[str]) -> list[dict]:
    cluster_rules = {
        "security": ["secure", "security", "encrypt", "safe", "protect"],
        "speed": ["fast", "speed", "quick", "rapid", "turbo"],
        "privacy": ["private", "privacy", "anonymous", "no log", "no track"],
        "streaming": ["stream", "netflix", "youtube", "hulu", "unblock"],
        "free": ["free", "unlimited", "no limit", "no cost"],
    }

    clusters = []
    assigned = set()

    for cluster_name, triggers in cluster_rules.items():
        matched = [
            kw for kw in keywords
            if any(trigger in kw.lower() for trigger in triggers) and kw not in assigned
        ]
        if matched:
            assigned.update(matched)
            clusters.append(
                {
                    "cluster_name": cluster_name,
                    "keywords": matched,
                    "matches_our_app": False,
                    "recommended": False,
                }
            )

    remaining = [kw for kw in keywords if kw not in assigned]
    if remaining:
        clusters.append(
            {
                "cluster_name": "other",
                "keywords": remaining[:20],
                "matches_our_app": False,
                "recommended": False,
            }
        )

    return clusters
