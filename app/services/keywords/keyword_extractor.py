"""Keyword extraction from text and Play Store search suggestions."""
import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Common English stopwords to filter out
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "your", "our", "their", "its", "this",
    "that", "these", "those", "it", "we", "you", "he", "she", "they", "i",
    "me", "him", "her", "us", "them", "get", "all", "more", "any", "also",
    "use", "using", "used", "into", "out", "up", "now", "just", "app",
    "free", "download", "install", "update", "new", "best", "top", "most",
}


def extract_keywords(text: str, max_ngram: int = 3) -> list[str]:
    """Extract keyword tokens (1-3 word n-grams) from text.

    Args:
        text: source text to extract from
        max_ngram: maximum n-gram size (default 3)

    Returns:
        list of unique keyword strings
    """
    if not text:
        return []

    # Lowercase, remove special characters
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if len(t) > 2 and t not in STOPWORDS]

    keywords = set()
    # Single words
    keywords.update(tokens)
    # 2-3 word n-grams
    for n in range(2, max_ngram + 1):
        for i in range(len(tokens) - n + 1):
            ngram = " ".join(tokens[i : i + n])
            keywords.add(ngram)

    return list(keywords)


def extract_from_competitors(competitor_data: list[dict], top_n: int = 100) -> dict[str, int]:
    """Extract and count keyword frequency across all competitor listings.

    Args:
        competitor_data: list of competitor metadata dicts
        top_n: return top N keywords by frequency

    Returns:
        dict mapping keyword → frequency count
    """
    counter: Counter = Counter()

    for comp in competitor_data:
        text_fields = [
            comp.get("title", ""),
            comp.get("short_description", ""),
            comp.get("long_description", ""),
        ]
        combined = " ".join(text_fields)
        for kw in extract_keywords(combined):
            counter[kw] += 1

    top = dict(counter.most_common(top_n))
    logger.info(f"Extracted {len(top)} keywords from {len(competitor_data)} competitors")
    return top


def get_play_store_suggestions(seed: str) -> list[str]:
    """Get Play Store / Google autocomplete suggestions for a seed keyword.

    Uses google-play-scraper search to infer popular related terms.
    Falls back to empty list on failure.

    Args:
        seed: seed keyword (e.g. "vpn")

    Returns:
        list of related keyword strings
    """
    try:
        from google_play_scraper import search

        results = search(seed, lang="en", country="us", n_hits=20)
        suggestions = []
        for r in results:
            title = r.get("title", "")
            summary = r.get("summary", "")
            for kw in extract_keywords(f"{title} {summary}"):
                if seed.lower() in kw.lower() and kw not in suggestions:
                    suggestions.append(kw)
        logger.info(f"Got {len(suggestions)} Play Store suggestions for seed={seed!r}")
        return suggestions[:30]
    except Exception as exc:
        logger.warning(f"Play Store suggestions failed for {seed!r}: {exc}")
        return []
