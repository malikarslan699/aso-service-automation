"""Policy engine: Google Play policy cache management."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Hardcoded Google Play Developer Policy summary (ASO-relevant rules)
POLICY_SUMMARY = """
Google Play Developer Policy — ASO-Relevant Rules (Effective 2024)

1. METADATA POLICY
   - App titles, icons, descriptions must accurately describe the app
   - No misleading claims about functionality or features
   - Descriptions must not include spam or repetitive keywords
   - No use of competitor brand names in your metadata
   - No unsubstantiated superlatives (e.g., "#1", "best", "fastest")

2. DECEPTIVE BEHAVIOR
   - Apps must not make false claims about their capabilities
   - No false security or privacy claims (e.g., "100% secure", "unhackable")
   - Claims about audits, certifications must be verifiable
   - No implied government or official endorsement

3. KEYWORD STUFFING
   - Descriptions cannot be keyword-stuffed or spammy
   - Repeated use of keywords to manipulate ranking is prohibited
   - Keywords must be naturally integrated

4. RATINGS AND REVIEWS
   - Review responses must be respectful and relevant
   - No incentivizing positive reviews
   - Do not post fake reviews

5. PRIVACY AND SECURITY
   - VPN apps must: disclose data collection, comply with encryption laws
   - No misleading privacy claims without evidence
   - "No logs" claims require independent audit certification

6. CONTENT POLICY
   - No hate speech, harassment, or misleading content in descriptions
   - No adult content in app metadata

Sources: Google Play Developer Program Policy (play.google.com/about/developer-content-policy)
"""


def get_policy_summary() -> str:
    """Return the current Google Play policy summary text."""
    return POLICY_SUMMARY.strip()


def update_policy_cache(db) -> bool:
    """Update (or create) the PolicyCache record with current policy text.

    Returns True if updated, False on error.
    """
    from sqlalchemy import select
    from app.models.policy_cache import PolicyCache

    try:
        policy_text = get_policy_summary()

        existing = db.execute(
            select(PolicyCache).where(PolicyCache.policy_type == "aso_policy")
        ).scalar_one_or_none()

        if existing:
            existing.content = policy_text
        else:
            db.add(PolicyCache(
                policy_type="aso_policy",
                content=policy_text,
                source_url="hardcoded",
            ))

        db.commit()
        logger.info("Policy cache updated successfully")
        return True

    except Exception as exc:
        logger.error(f"Failed to update policy cache: {exc}")
        return False


def get_cached_policy(db) -> str:
    """Retrieve cached policy text from DB, fallback to hardcoded."""
    from sqlalchemy import select
    from app.models.policy_cache import PolicyCache

    try:
        cached = db.execute(
            select(PolicyCache).where(PolicyCache.policy_type == "aso_policy")
        ).scalar_one_or_none()
        if cached and cached.content:
            return cached.content
    except Exception:
        pass

    return get_policy_summary()
