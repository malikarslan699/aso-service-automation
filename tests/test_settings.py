from httpx import AsyncClient


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
