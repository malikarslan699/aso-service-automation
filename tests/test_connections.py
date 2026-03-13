"""Tests for app connection verification endpoints."""
from httpx import AsyncClient


async def test_google_play_connection_check_without_credential(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Conn Test App", "package_name": "com.test.connection", "store": "google_play"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    app_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/apps/{app_id}/connections/google-play", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["provider"] == "google_play"
    assert "not configured" in data["message"].lower()


async def test_google_play_connection_check_requires_auth(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Conn Test App 2", "package_name": "com.test.connection.two", "store": "google_play"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    app_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/apps/{app_id}/connections/google-play")
    assert resp.status_code == 403
