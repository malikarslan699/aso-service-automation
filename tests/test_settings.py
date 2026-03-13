import pytest
from httpx import AsyncClient

from app.config import DEFAULT_SECRET_KEY, Settings


async def test_settings_global_defaults_present(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/settings/global", headers=auth_headers)
    assert resp.status_code == 200

    keys = {item["key"] for item in resp.json()}
    expected = {
        "anthropic_api_key",
        "openai_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
        "serpapi_key",
        "google_service_account_json",
        "google_play_package_name",
        "google_api_discovery_url",
        "dry_run",
        "publish_mode",
        "human_sim_enabled",
        "max_publish_per_day",
        "max_publish_per_week",
        "auto_approve_threshold",
    }
    assert expected.issubset(keys)


async def test_integrations_status_endpoint(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/settings/integrations/status", headers=auth_headers)
    assert resp.status_code == 200
    providers = {item["provider"] for item in resp.json()["integrations"]}
    assert {"anthropic", "openai", "telegram", "serpapi", "google_play"}.issubset(providers)


async def test_integrations_check_endpoint_runs(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/settings/integrations/check",
        headers=auth_headers,
        json={"provider": "all"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) >= 5


async def test_ai_balance_endpoint_returns_shape(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/settings/ai-balance", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert "status" in data
    assert "balance_usd" in data
    assert "message" in data


async def test_publish_mode_patch_updates_config(client: AsyncClient, auth_headers):
    resp = await client.patch(
        "/api/v1/settings/publish-mode",
        headers=auth_headers,
        json={"mode": "soft", "auto_approve": True},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["publish_mode"] == "soft"
    assert payload["auto_approve"] is True

    cfg_resp = await client.get("/api/v1/settings/global", headers=auth_headers)
    assert cfg_resp.status_code == 200
    by_key = {item["key"]: item["value"] for item in cfg_resp.json()}
    assert by_key["publish_mode"] == "soft"
    assert by_key["manual_approval_required"] == "false"


async def test_publish_limits_validation_rejects_weekly_below_daily(client: AsyncClient, auth_headers):
    week_ok = await client.put(
        "/api/v1/settings/global",
        headers=auth_headers,
        json={"key": "max_publish_per_week", "value": "15"},
    )
    assert week_ok.status_code == 200

    day_resp = await client.put(
        "/api/v1/settings/global",
        headers=auth_headers,
        json={"key": "max_publish_per_day", "value": "10"},
    )
    assert day_resp.status_code == 200

    week_resp = await client.put(
        "/api/v1/settings/global",
        headers=auth_headers,
        json={"key": "max_publish_per_week", "value": "9"},
    )
    assert week_resp.status_code == 400
    assert "max_publish_per_week" in week_resp.json()["detail"]


def test_settings_reject_default_secret_in_live_mode():
    with pytest.raises(ValueError, match="SECRET_KEY must be changed"):
        Settings(secret_key=DEFAULT_SECRET_KEY, dry_run=False)


def test_settings_allow_default_secret_in_dry_run_mode():
    settings = Settings(secret_key=DEFAULT_SECRET_KEY, dry_run=True)
    assert settings.secret_key == DEFAULT_SECRET_KEY
