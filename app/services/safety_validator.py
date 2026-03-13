"""Safety validator: 3-layer validation for ASO suggestions."""
import json
import re
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Layer A: Hard-blocked terms (case-insensitive)
BLOCKED_TERMS = [
    "unhackable", "100% secure", "unbreakable", "impenetrable",
    "100% safe", "completely safe", "totally safe",
    "#1 vpn", "number one vpn", "best vpn", "top vpn",
    "guaranteed", "100% guarantee", "money back guarantee",
    "nordvpn", "expressvpn", "surfshark", "protonvpn", "pia vpn",
    "private internet access", "mullvad", "ivpn", "ipvanish",
    "competitor", "unlike other vpns", "better than",
    "fda approved", "government approved", "certified by",
]

# Layer B: Claims that require app_fact evidence
CLAIM_TO_FACT = {
    "military grade": "encryption_type",
    "military-grade": "encryption_type",
    "aes-256": "encryption_type",
    "256-bit": "encryption_type",
    "no logs": "no_logs_audited",
    "no-logs": "no_logs_audited",
    "zero logs": "no_logs_audited",
    "zero-logs": "no_logs_audited",
    "log free": "no_logs_audited",
    "no data collection": "no_logs_audited",
    "kill switch": "kill_switch",
    "killswitch": "kill_switch",
    "dns leak": "dns_leak_protection",
    "dns protection": "dns_leak_protection",
    "open source": "open_source",
    "audited": "no_logs_audited",
    "independently audited": "no_logs_audited",
}

# Layer C: Field length limits
FIELD_LIMITS = {
    "title": 30,
    "short_description": 80,
    "long_description": 4000,
    "reply_text": 280,
}


def validate(
    suggestion: dict,
    app_facts: list[dict],
    recent_suggestions: list[dict],
) -> dict:
    """Validate a suggestion through 3 safety layers.

    Args:
        suggestion: {suggestion_type, field_name, new_value, old_value}
        app_facts: [{fact_key, fact_value}]
        recent_suggestions: recent approved/published suggestions for same app

    Returns:
        {passed: bool, risk_score: int (0-3), reasons: list[str], layer_results: dict}
    """
    reasons = []
    layer_results = {}

    # Layer A
    layer_a = _check_layer_a(suggestion["new_value"])
    layer_results["layer_a"] = layer_a
    if not layer_a["passed"]:
        reasons.extend(layer_a["reasons"])

    # Layer B
    layer_b = _check_layer_b(suggestion["new_value"], app_facts)
    layer_results["layer_b"] = layer_b
    if not layer_b["passed"]:
        reasons.extend(layer_b["reasons"])

    # Layer C
    layer_c = _check_layer_c(suggestion, recent_suggestions)
    layer_results["layer_c"] = layer_c
    if not layer_c["passed"]:
        reasons.extend(layer_c["reasons"])

    # Determine risk score
    if not layer_a["passed"]:
        risk_score = 3  # Hard block
    elif not layer_b["passed"]:
        risk_score = 2  # Evidence missing
    elif not layer_c["passed"]:
        risk_score = 1  # Behavior warning
    else:
        risk_score = 0  # Clean

    passed = risk_score == 0

    return {
        "passed": passed,
        "risk_score": risk_score,
        "reasons": reasons,
        "layer_results": layer_results,
    }


def _check_layer_a(text: str) -> dict:
    """Layer A: Hard block list check."""
    text_lower = text.lower()
    blocked = []

    for term in BLOCKED_TERMS:
        if term.lower() in text_lower:
            blocked.append(term)

    return {
        "passed": len(blocked) == 0,
        "reasons": [f"Blocked term: '{t}'" for t in blocked],
        "blocked_terms": blocked,
    }


def _check_layer_b(text: str, app_facts: list[dict]) -> dict:
    """Layer B: Evidence check — claims must be backed by app_facts."""
    text_lower = text.lower()
    missing_evidence = []

    # Build fact keys set for quick lookup
    fact_keys = {f["fact_key"].lower() for f in app_facts if f.get("verified", False)}

    for claim, required_fact in CLAIM_TO_FACT.items():
        if claim.lower() in text_lower:
            if required_fact.lower() not in fact_keys:
                missing_evidence.append(
                    f"Claim '{claim}' requires app_fact '{required_fact}' (not found or unverified)"
                )

    return {
        "passed": len(missing_evidence) == 0,
        "reasons": missing_evidence,
    }


def _check_layer_c(suggestion: dict, recent_suggestions: list[dict]) -> dict:
    """Layer C: Behavior rules — length, keyword density, frequency limits."""
    reasons = []
    text = suggestion.get("new_value", "")
    field_name = suggestion.get("field_name", "")
    suggestion_type = suggestion.get("suggestion_type", "")

    # Check field length
    limit = FIELD_LIMITS.get(field_name)
    if limit and len(text) > limit:
        reasons.append(f"Field '{field_name}' exceeds {limit} chars (got {len(text)})")

    # Check keyword stuffing (any word repeated >3 times)
    words = re.sub(r"[^a-z0-9\s]", " ", text.lower()).split()
    word_counts: dict[str, int] = {}
    for word in words:
        if len(word) >= 3:
            word_counts[word] = word_counts.get(word, 0) + 1

    stuffed = [w for w, c in word_counts.items() if c > 3]
    if stuffed:
        reasons.append(f"Keyword stuffing detected: {stuffed[:3]}")

    # Check frequency limits per suggestion type
    if suggestion_type == "listing" and field_name == "title":
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        recent_title_changes = [
            s for s in recent_suggestions
            if s.get("field_name") == "title"
            and s.get("status") in ("approved", "published")
            and _parse_date(s.get("created_at", "")) > cutoff
        ]
        if recent_title_changes:
            reasons.append(
                f"Title was changed {len(recent_title_changes)} time(s) in the last 30 days (max 1)"
            )

    elif suggestion_type == "listing" and field_name in ("short_description", "long_description"):
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=14)
        recent_desc_changes = [
            s for s in recent_suggestions
            if s.get("field_name") == field_name
            and s.get("status") in ("approved", "published")
            and _parse_date(s.get("created_at", "")) > cutoff
        ]
        if recent_desc_changes:
            reasons.append(
                f"'{field_name}' changed {len(recent_desc_changes)} time(s) in last 14 days (max 1)"
            )

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }


def _parse_date(date_str: str) -> datetime:
    """Safely parse ISO date string, return epoch on failure."""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc).replace(tzinfo=None)
