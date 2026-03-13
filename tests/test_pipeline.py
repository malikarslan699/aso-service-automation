"""Integration tests for pipeline-related functionality (mocked services)."""
import pytest
import json
from unittest.mock import patch, MagicMock
from app.services.safety_validator import validate
from app.services.auto_approve_engine import should_auto_approve, update_rules


# --- Safety Validator Integration ---

class TestSafetyValidatorIntegration:
    def test_review_reply_clean(self):
        suggestion = {
            "suggestion_type": "review_reply",
            "field_name": "reply_text",
            "new_value": "Thank you for your review! We're glad you enjoy using our VPN.",
            "old_value": "",
        }
        result = validate(suggestion, [], [])
        assert result["risk_score"] == 0
        assert result["passed"] is True

    def test_listing_with_competitor_name(self):
        suggestion = {
            "suggestion_type": "listing",
            "field_name": "title",
            "new_value": "Better than NordVPN",
            "old_value": "Old Title",
        }
        result = validate(suggestion, [], [])
        assert result["risk_score"] == 3
        assert result["passed"] is False

    def test_listing_valid_with_facts(self):
        facts = [
            {"fact_key": "encryption_type", "fact_value": "AES-256", "verified": True},
            {"fact_key": "kill_switch", "fact_value": "yes", "verified": True},
        ]
        suggestion = {
            "suggestion_type": "listing",
            "field_name": "short_description",
            "new_value": "Protect privacy with military grade encryption and kill switch.",
            "old_value": "",
        }
        result = validate(suggestion, facts, [])
        assert result["passed"] is True

    def test_safety_result_json_serializable(self):
        suggestion = {
            "suggestion_type": "listing",
            "field_name": "title",
            "new_value": "Fast VPN",
            "old_value": "Old VPN",
        }
        result = validate(suggestion, [], [])
        # Should be JSON-serializable (for storage in DB)
        assert json.dumps(result) is not None


# --- Auto-Approve Engine Integration ---

class TestAutoApproveEngine:
    def test_auto_approve_review_reply_risk_0(self):
        suggestion = {"suggestion_type": "review_reply", "risk_score": 0}
        active_rule = MagicMock()
        active_rule.suggestion_type = "review_reply"
        active_rule.is_active = True
        active_rule.max_risk_score = 0

        assert should_auto_approve(suggestion, [active_rule]) is True

    def test_no_auto_approve_without_rule(self):
        suggestion = {"suggestion_type": "review_reply", "risk_score": 0}
        assert should_auto_approve(suggestion, []) is False

    def test_no_auto_approve_listing_type(self):
        suggestion = {"suggestion_type": "listing", "risk_score": 0}
        active_rule = MagicMock()
        active_rule.suggestion_type = "listing"
        active_rule.is_active = True
        active_rule.max_risk_score = 0
        # listing type is not in AUTO_APPROVE_TYPES
        assert should_auto_approve(suggestion, [active_rule]) is False

    def test_no_auto_approve_risk_1(self):
        suggestion = {"suggestion_type": "review_reply", "risk_score": 1}
        active_rule = MagicMock()
        active_rule.suggestion_type = "review_reply"
        active_rule.is_active = True
        active_rule.max_risk_score = 0  # Max 0, but suggestion is risk 1

        assert should_auto_approve(suggestion, [active_rule]) is False

    def test_no_auto_approve_inactive_rule(self):
        suggestion = {"suggestion_type": "review_reply", "risk_score": 0}
        inactive_rule = MagicMock()
        inactive_rule.suggestion_type = "review_reply"
        inactive_rule.is_active = False
        inactive_rule.max_risk_score = 0

        assert should_auto_approve(suggestion, [inactive_rule]) is False


# --- Pipeline Data Flow (without DB, mocked) ---

class TestPipelineDataFlow:
    def test_suggestion_risk_assignment(self):
        """Test that suggestions get correct risk scores from safety validator."""
        suggestions = [
            {
                "suggestion_type": "listing",
                "field_name": "title",
                "new_value": "Unhackable VPN",  # Should get risk 3
                "old_value": "VPN",
            },
            {
                "suggestion_type": "review_reply",
                "field_name": "reply_text",
                "new_value": "Thank you for your kind review!",  # Should get risk 0
                "old_value": "",
            },
            {
                "suggestion_type": "listing",
                "field_name": "title",
                "new_value": "Fast VPN",  # Should get risk 0
                "old_value": "Old VPN",
            },
        ]

        results = []
        for s in suggestions:
            result = validate(s, [], [])
            results.append((s["new_value"], result["risk_score"]))

        # Check expected risk scores
        assert results[0][1] == 3  # "Unhackable VPN" → risk 3
        assert results[1][1] == 0  # Clean review reply → risk 0
        assert results[2][1] == 0  # "Fast VPN" → risk 0

    def test_high_risk_filtered_for_review(self):
        """Only risk 2+ suggestions should be sent for human review."""
        suggestions_with_risk = [
            {"id": 1, "risk_score": 0, "status": "pending"},
            {"id": 2, "risk_score": 1, "status": "pending"},
            {"id": 3, "risk_score": 2, "status": "pending"},
            {"id": 4, "risk_score": 3, "status": "pending"},
        ]

        high_risk = [s for s in suggestions_with_risk if s["risk_score"] >= 2]
        assert len(high_risk) == 2
        assert all(s["risk_score"] >= 2 for s in high_risk)

    def test_safety_result_stored_as_json(self):
        """Verify safety results can be stored as JSON string."""
        suggestion = {
            "suggestion_type": "listing",
            "field_name": "short_description",
            "new_value": "Secure VPN app",
            "old_value": "",
        }
        result = validate(suggestion, [], [])
        json_str = json.dumps(result)
        restored = json.loads(json_str)

        assert restored["passed"] == result["passed"]
        assert restored["risk_score"] == result["risk_score"]
