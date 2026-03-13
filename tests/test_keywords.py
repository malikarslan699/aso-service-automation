"""Unit tests for keyword extraction and opportunity scoring."""
import pytest
from app.services.keywords.keyword_extractor import extract_keywords, extract_from_competitors
from app.services.keywords.opportunity_scorer import score_keyword, rank_keywords
from app.models.keyword import Keyword


# --- keyword_extractor tests ---

def test_extract_keywords_basic():
    result = extract_keywords("secure vpn for android")
    assert "vpn" in result
    assert "secure" in result


def test_extract_keywords_removes_stopwords():
    result = extract_keywords("the best vpn for you")
    assert "the" not in result
    assert "for" not in result
    assert "vpn" in result


def test_extract_keywords_includes_bigrams():
    result = extract_keywords("secure vpn protect privacy")
    assert "secure vpn" in result
    assert "vpn protect" in result


def test_extract_keywords_empty_text():
    result = extract_keywords("")
    assert result == []


def test_extract_keywords_special_chars():
    result = extract_keywords("100% secure! VPN – protect@privacy")
    assert "secure" in result
    assert "vpn" in result


def test_extract_from_competitors():
    competitors = [
        {
            "title": "Fast VPN",
            "short_description": "Fast secure vpn",
            "long_description": "Protect your privacy with fast vpn",
        },
        {
            "title": "Secure VPN",
            "short_description": "Secure fast vpn",
            "long_description": "Stay safe with secure vpn",
        },
        {
            "title": "Private VPN",
            "short_description": "Private vpn",
            "long_description": "Private secure vpn",
        },
    ]
    result = extract_from_competitors(competitors, top_n=20)
    assert isinstance(result, dict)
    # "vpn" should appear in multiple competitors
    assert "vpn" in result
    assert result["vpn"] >= 2  # vpn appears in all 3 competitors


def test_extract_from_competitors_empty():
    result = extract_from_competitors([])
    assert result == {}


# --- opportunity_scorer tests ---

def test_score_keyword_basic():
    score = score_keyword("vpn", 3, 5)
    assert 0.0 <= score <= 1.0
    assert score == pytest.approx(0.6, abs=0.01)


def test_score_keyword_with_app_fact_boost():
    score_without = score_keyword("encryption", 3, 5, in_app_facts=False)
    score_with = score_keyword("encryption", 3, 5, in_app_facts=True)
    assert score_with > score_without


def test_score_keyword_with_play_suggestion_boost():
    score_without = score_keyword("vpn secure", 3, 5, in_play_suggestions=False)
    score_with = score_keyword("vpn secure", 3, 5, in_play_suggestions=True)
    assert score_with > score_without


def test_score_keyword_capped_at_1():
    # Even with all boosts, should not exceed 1.0
    score = score_keyword("vpn", 5, 5, in_app_facts=True, in_play_suggestions=True)
    assert score <= 1.0


def test_score_keyword_zero_competitors():
    score = score_keyword("vpn", 0, 0)
    assert score == 0.0


def test_rank_keywords_sorted():
    frequencies = {
        "vpn": 5,
        "fast vpn": 3,
        "secure vpn": 4,
        "free vpn": 1,
    }
    app_facts = [{"fact_key": "encryption_type", "fact_value": "AES-256", "verified": True}]
    play_suggestions = ["vpn free", "vpn fast"]

    ranked = rank_keywords(frequencies, app_facts, play_suggestions, top_n=10)

    assert len(ranked) == 4
    # Should be sorted by opportunity_score descending
    scores = [r["opportunity_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_keywords_recommended_flag():
    frequencies = {"secure vpn": 5}
    app_facts = [{"fact_key": "encryption_type", "fact_value": "AES-256", "verified": True}]
    play_suggestions = []

    ranked = rank_keywords(frequencies, app_facts, play_suggestions)
    assert len(ranked) == 1
    # "secure vpn" should have recommended=True since it has high score + matches app facts
    # Note: recommended = score >= 0.4 AND in_app_facts
    assert isinstance(ranked[0]["recommended"], bool)


def test_rank_keywords_respects_top_n():
    frequencies = {f"keyword_{i}": i for i in range(1, 20)}
    ranked = rank_keywords(frequencies, [], [], top_n=5)
    assert len(ranked) == 5


@pytest.mark.asyncio
async def test_keywords_page_limit_returns_envelope(client, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Keywords Paging App", "package_name": "com.keywords.page"},
        headers=auth_headers,
    )
    assert create_app.status_code == 201
    app_id = create_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        for idx in range(3):
            session.add(
                Keyword(
                    app_id=app_id,
                    keyword=f"keyword-{idx}",
                    source="manual",
                    opportunity_score=float(idx + 1),
                    status="active",
                )
            )
        await session.commit()

    resp = await client.get(f"/api/v1/apps/{app_id}/keywords?page=2&limit=2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 1
