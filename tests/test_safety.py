"""Unit tests for the safety validator (3 layers)."""
import pytest
from app.services.safety_validator import validate, _check_layer_a, _check_layer_b, _check_layer_c


# --- Sample data ---

VERIFIED_FACTS = [
    {"fact_key": "encryption_type", "fact_value": "AES-256", "verified": True},
    {"fact_key": "kill_switch", "fact_value": "yes", "verified": True},
    {"fact_key": "no_logs_audited", "fact_value": "yes", "verified": True},
]

EMPTY_FACTS = []

NO_RECENT = []


# --- Layer A Tests ---

def test_layer_a_passes_clean_text():
    result = _check_layer_a("Secure VPN for Android")
    assert result["passed"] is True
    assert result["blocked_terms"] == []


def test_layer_a_blocks_unhackable():
    result = _check_layer_a("The unhackable VPN app")
    assert result["passed"] is False
    assert "unhackable" in result["blocked_terms"]


def test_layer_a_blocks_competitor_name():
    result = _check_layer_a("Better than NordVPN")
    assert result["passed"] is False
    assert any("nordvpn" in t.lower() for t in result["blocked_terms"])


def test_layer_a_blocks_100_percent_secure():
    result = _check_layer_a("Get 100% secure browsing today")
    assert result["passed"] is False


def test_layer_a_case_insensitive():
    result = _check_layer_a("UNHACKABLE protection")
    assert result["passed"] is False


# --- Layer B Tests ---

def test_layer_b_passes_no_claims():
    result = _check_layer_b("Fast VPN for Android", VERIFIED_FACTS)
    assert result["passed"] is True


def test_layer_b_passes_claim_with_evidence():
    # "military grade" requires encryption_type fact — which is in VERIFIED_FACTS
    result = _check_layer_b("Military grade encryption", VERIFIED_FACTS)
    assert result["passed"] is True


def test_layer_b_blocks_claim_without_evidence():
    # No facts at all
    result = _check_layer_b("Military grade encryption protects you", EMPTY_FACTS)
    assert result["passed"] is False
    assert any("military grade" in r.lower() for r in result["reasons"])


def test_layer_b_blocks_no_logs_without_audit():
    result = _check_layer_b("We have a no logs policy", EMPTY_FACTS)
    assert result["passed"] is False


def test_layer_b_passes_no_logs_with_audit_fact():
    result = _check_layer_b("We have a no logs policy", VERIFIED_FACTS)
    assert result["passed"] is True


def test_layer_b_blocks_unverified_fact():
    # Fact exists but verified=False
    unverified_facts = [{"fact_key": "no_logs_audited", "fact_value": "yes", "verified": False}]
    result = _check_layer_b("We have a no logs policy", unverified_facts)
    assert result["passed"] is False


# --- Layer C Tests ---

def test_layer_c_passes_valid_title():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "title",
        "new_value": "NetSafe VPN – Fast & Secure",
        "old_value": "",
    }
    result = _check_layer_c(suggestion, NO_RECENT)
    assert result["passed"] is True


def test_layer_c_blocks_title_too_long():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "title",
        "new_value": "This Is A Very Very Very Long Title That Exceeds The Limit",
        "old_value": "",
    }
    result = _check_layer_c(suggestion, NO_RECENT)
    assert result["passed"] is False
    assert any("30 char" in r or "exceeds" in r.lower() for r in result["reasons"])


def test_layer_c_blocks_keyword_stuffing():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "long_description",
        "new_value": "vpn vpn vpn vpn vpn secure fast",
        "old_value": "",
    }
    result = _check_layer_c(suggestion, NO_RECENT)
    assert result["passed"] is False
    assert any("stuffing" in r.lower() for r in result["reasons"])


def test_layer_c_passes_review_reply():
    suggestion = {
        "suggestion_type": "review_reply",
        "field_name": "reply_text",
        "new_value": "Thank you for your feedback! We appreciate your support.",
        "old_value": "",
    }
    result = _check_layer_c(suggestion, NO_RECENT)
    assert result["passed"] is True


# --- Full validate() Tests ---

def test_validate_clean_suggestion():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "short_description",
        "new_value": "Secure VPN to protect your privacy online.",
        "old_value": "Old description",
    }
    result = validate(suggestion, VERIFIED_FACTS, NO_RECENT)
    assert result["risk_score"] == 0
    assert result["passed"] is True
    assert result["reasons"] == []


def test_validate_blocked_term_gives_risk_3():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "title",
        "new_value": "Unhackable VPN",
        "old_value": "NetSafe",
    }
    result = validate(suggestion, VERIFIED_FACTS, NO_RECENT)
    assert result["risk_score"] == 3
    assert result["passed"] is False


def test_validate_missing_evidence_gives_risk_2():
    suggestion = {
        "suggestion_type": "listing",
        "field_name": "short_description",
        "new_value": "Military grade encryption for your protection",
        "old_value": "Simple description",
    }
    result = validate(suggestion, EMPTY_FACTS, NO_RECENT)
    # Layer A passes (military grade not in blocked list)
    # Layer B fails (no encryption_type fact)
    assert result["risk_score"] == 2
    assert result["passed"] is False


def test_validate_layer_results_present():
    suggestion = {
        "suggestion_type": "review_reply",
        "field_name": "reply_text",
        "new_value": "Thanks for the review!",
        "old_value": "",
    }
    result = validate(suggestion, VERIFIED_FACTS, NO_RECENT)
    assert "layer_results" in result
    assert "layer_a" in result["layer_results"]
    assert "layer_b" in result["layer_results"]
    assert "layer_c" in result["layer_results"]
