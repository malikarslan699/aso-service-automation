"""AI engine: generate ASO suggestions with provider analytics and fallback."""
from __future__ import annotations

import logging
from typing import Optional

from app.services.ai_provider import (
    anthropic_complete,
    extract_json_object,
    openai_complete,
)

logger = logging.getLogger(__name__)

TITLE_MAX = 30
SHORT_DESC_MAX = 80
LONG_DESC_MAX = 4000
REVIEW_REPLY_MAX = 280


def generate_suggestions(
    app_facts: list[dict],
    current_listing: dict,
    top_keywords: list[dict],
    anthropic_api_key: str,
    openai_api_key: str = "",
    reviews: Optional[list[dict]] = None,
) -> dict:
    if not anthropic_api_key and not openai_api_key:
        return _empty_result("No AI provider configured", "provider_error", "provider_error")

    facts_text = "\n".join(f"- {fact['fact_key']}: {fact['fact_value']}" for fact in app_facts) or "No facts provided"
    top_kw_text = ", ".join(kw["keyword"] for kw in top_keywords[:15] if kw.get("recommended")) or ", ".join(
        kw["keyword"] for kw in top_keywords[:10]
    )
    reviews = reviews or []

    review_items = [
        {
            "review_id": review.get("review_id", ""),
            "score": review.get("score", 3),
            "content": review.get("content", ""),
        }
        for review in reviews[:5]
        if not review.get("reply_content")
    ]

    prompt = f"""You are an expert ASO specialist for a Google Play VPN app.

App facts:
{facts_text}

Current listing:
- Title: {current_listing.get("title", "")}
- Short description: {current_listing.get("short_description", "")}
- Long description preview: {current_listing.get("long_description", "")[:700]}

Top opportunity keywords:
{top_kw_text}

Pending review replies to draft:
{review_items if review_items else "[]"}

Return ONLY valid JSON with this exact shape:
{{
  "title": {{"new_value": "...", "reasoning": "...", "confidence": 0.0}},
  "short_description": {{"new_value": "...", "reasoning": "...", "confidence": 0.0}},
  "long_description": {{"new_value": "...", "reasoning": "...", "confidence": 0.0}},
  "review_replies": [
    {{"review_id": "...", "new_value": "...", "reasoning": "...", "confidence": 0.0}}
  ]
}}

Rules:
- Title max {TITLE_MAX} chars
- Short description max {SHORT_DESC_MAX} chars
- Long description max {LONG_DESC_MAX} chars
- Review reply max {REVIEW_REPLY_MAX} chars
- Only make claims supported by app facts
- No competitor names
- No false claims
- If a field cannot be improved safely, return an empty string for that field
"""

    provider_attempts = []
    if anthropic_api_key:
        provider_attempts.append(("anthropic", anthropic_complete(prompt, 2200, anthropic_api_key)))
    if openai_api_key:
        provider_attempts.append(("openai", openai_complete(prompt, 1800, openai_api_key)))

    first_failure = None
    first_provider = None
    for provider_name, result in provider_attempts:
        if result["ok"]:
            try:
                parsed = extract_json_object(result["text"])
            except Exception as exc:
                logger.warning("AI provider %s returned invalid JSON: %s", provider_name, exc)
                result = {
                    **result,
                    "ok": False,
                    "status": "provider_error",
                    "error_class": "provider_error",
                    "error_message": "Could not parse provider response",
                }
                if first_failure is None:
                    first_failure = result
                    first_provider = provider_name
                continue
            suggestions = _normalize_suggestions(parsed, current_listing, review_items)
            fallback_used = bool(anthropic_api_key) and provider_name == "openai"
            value_summary = _build_value_summary(
                provider_name=result["provider"],
                suggestions_generated=len(suggestions),
                estimated_cost=result["estimated_cost"],
                fallback_used=fallback_used,
            )
            return {
                "suggestions": suggestions,
                "provider_name": result["provider"],
                "fallback_provider_name": "openai" if fallback_used else None,
                "provider_status": result["status"],
                "provider_error_class": None,
                "estimated_cost": result["estimated_cost"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "value_summary": value_summary,
                "message": f"{result['provider'].title()} generated {len(suggestions)} suggestion(s).",
                "raw_provider_message": None,
            }

        if first_failure is None:
            first_failure = result
            first_provider = provider_name
        logger.warning("AI provider %s failed: %s", provider_name, result["error_message"])

    if first_failure is None:
        return _empty_result("AI generation returned 0 suggestions.", "provider_error", "provider_error")

    return {
        "suggestions": [],
        "provider_name": first_failure["provider"],
        "fallback_provider_name": "openai" if first_provider == "anthropic" and openai_api_key else None,
        "provider_status": first_failure["status"],
        "provider_error_class": first_failure["error_class"],
        "estimated_cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "value_summary": _build_value_summary(
            provider_name=first_failure["provider"],
            suggestions_generated=0,
            estimated_cost=0.0,
            fallback_used=bool(anthropic_api_key and openai_api_key),
        ),
        "message": first_failure["error_message"] or "AI generation failed",
        "raw_provider_message": first_failure["error_message"],
    }


def _empty_result(message: str, status: str, error_class: str) -> dict:
    return {
        "suggestions": [],
        "provider_name": None,
        "fallback_provider_name": None,
        "provider_status": status,
        "provider_error_class": error_class,
        "estimated_cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "value_summary": "No AI provider output was produced.",
        "message": message,
        "raw_provider_message": message,
    }


def _normalize_suggestions(parsed: dict, current_listing: dict, review_items: list[dict]) -> list[dict]:
    suggestions: list[dict] = []

    def add_listing(field_name: str, old_value: str, max_chars: int) -> None:
        item = parsed.get(field_name) or {}
        new_value = str(item.get("new_value", "")).strip()
        if not new_value or len(new_value) > max_chars:
            return
        suggestions.append(
            {
                "suggestion_type": "listing",
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "reasoning": str(item.get("reasoning", "")),
                "confidence": float(item.get("confidence", 0.7) or 0.7),
            }
        )

    add_listing("title", current_listing.get("title", ""), TITLE_MAX)
    add_listing("short_description", current_listing.get("short_description", ""), SHORT_DESC_MAX)
    add_listing("long_description", current_listing.get("long_description", ""), LONG_DESC_MAX)

    known_review_ids = {item["review_id"] for item in review_items}
    for reply in parsed.get("review_replies") or []:
        review_id = str(reply.get("review_id", "")).strip()
        new_value = str(reply.get("new_value", "")).strip()
        if not review_id or review_id not in known_review_ids or not new_value or len(new_value) > REVIEW_REPLY_MAX:
            continue
        suggestions.append(
            {
                "suggestion_type": "review_reply",
                "field_name": "reply_text",
                "old_value": "",
                "new_value": new_value,
                "reasoning": str(reply.get("reasoning", "")),
                "confidence": float(reply.get("confidence", 0.8) or 0.8),
                "extra": {"review_id": review_id},
            }
        )

    return suggestions


def _build_value_summary(provider_name: str | None, suggestions_generated: int, estimated_cost: float, fallback_used: bool) -> str:
    provider = provider_name or "no provider"
    fallback_note = " Fallback was used." if fallback_used else ""
    return (
        f"{provider.title()} produced {suggestions_generated} suggestion(s) "
        f"for an estimated ${estimated_cost:.4f}.{fallback_note}"
    )
