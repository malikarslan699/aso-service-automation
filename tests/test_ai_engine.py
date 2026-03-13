from app.services import ai_engine


def test_generate_suggestions_falls_back_to_openai(monkeypatch):
    monkeypatch.setattr(
        ai_engine,
        "anthropic_complete",
        lambda *args, **kwargs: {
            "ok": False,
            "provider": "anthropic",
            "status": "billing_blocked",
            "error_class": "billing_blocked",
            "error_message": "credits low",
            "estimated_cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
    )
    monkeypatch.setattr(
        ai_engine,
        "openai_complete",
        lambda *args, **kwargs: {
            "ok": True,
            "provider": "openai",
            "status": "inference_healthy",
            "text": """
            {
              "title": {"new_value": "Safe VPN Pro", "reasoning": "better", "confidence": 0.8},
              "short_description": {"new_value": "Fast secure VPN", "reasoning": "better", "confidence": 0.8},
              "long_description": {"new_value": "Detailed safe description", "reasoning": "better", "confidence": 0.8},
              "review_replies": []
            }
            """,
            "estimated_cost": 0.0123,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    )

    result = ai_engine.generate_suggestions(
        app_facts=[{"fact_key": "feature", "fact_value": "vpn"}],
        current_listing={"title": "Old title", "short_description": "Old short", "long_description": "Old long"},
        top_keywords=[{"keyword": "vpn", "recommended": True}],
        anthropic_api_key="sk-ant",
        openai_api_key="sk-openai",
        reviews=[],
    )

    assert result["provider_name"] == "openai"
    assert result["fallback_provider_name"] == "openai"
    assert result["suggestions"]
    assert result["estimated_cost"] == 0.0123


def test_generate_suggestions_reports_provider_failure(monkeypatch):
    monkeypatch.setattr(
        ai_engine,
        "anthropic_complete",
        lambda *args, **kwargs: {
            "ok": False,
            "provider": "anthropic",
            "status": "billing_blocked",
            "error_class": "billing_blocked",
            "error_message": "credits low",
            "estimated_cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        },
    )

    result = ai_engine.generate_suggestions(
        app_facts=[],
        current_listing={"title": "", "short_description": "", "long_description": ""},
        top_keywords=[],
        anthropic_api_key="sk-ant",
        openai_api_key="",
        reviews=[],
    )

    assert result["suggestions"] == []
    assert result["provider_status"] == "billing_blocked"
    assert result["provider_error_class"] == "billing_blocked"
