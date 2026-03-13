import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_app(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Test App", "package_name": "com.test.app"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test App"
    assert data["package_name"] == "com.test.app"
    assert data["status"] == "active"
    assert data["owner_user_id"] is not None


@pytest.mark.asyncio
async def test_list_apps(client: AsyncClient, auth_headers):
    # Create an app first
    await client.post(
        "/api/v1/apps",
        json={"name": "List Test", "package_name": "com.list.test"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/apps", headers=auth_headers)
    assert response.status_code == 200
    apps = response.json()
    assert len(apps) >= 1


@pytest.mark.asyncio
async def test_create_duplicate_app(client: AsyncClient, auth_headers):
    await client.post(
        "/api/v1/apps",
        json={"name": "Dup App", "package_name": "com.dup.app"},
        headers=auth_headers,
    )
    response = await client.post(
        "/api/v1/apps",
        json={"name": "Dup App 2", "package_name": "com.dup.app"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_app(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Get Test", "package_name": "com.get.test"},
        headers=auth_headers,
    )
    app_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/apps/{app_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Get Test"


@pytest.mark.asyncio
async def test_update_app(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Update Test", "package_name": "com.update.test"},
        headers=auth_headers,
    )
    app_id = create_resp.json()["id"]
    response = await client.patch(
        f"/api/v1/apps/{app_id}",
        json={"name": "Updated Name", "status": "paused"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_upload_service_account_credential_defaults_to_json_type(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Cred App", "package_name": "com.cred.app"},
        headers=auth_headers,
    )
    app_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/apps/{app_id}/credentials",
        headers=auth_headers,
        files={"file": ("service-account.json", '{"type":"service_account"}', "application/json")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["credential_type"] == "service_account_json"


@pytest.mark.asyncio
async def test_upload_service_account_rejects_invalid_json(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Bad Cred App", "package_name": "com.badcred.app"},
        headers=auth_headers,
    )
    app_id = create_resp.json()["id"]

    response = await client.post(
        f"/api/v1/apps/{app_id}/credentials",
        headers=auth_headers,
        params={"credential_type": "service_account_json"},
        files={"file": ("broken.json", "{not-valid", "application/json")},
    )
    assert response.status_code == 400
    assert "Invalid JSON file" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sub_admin_can_create_own_app_and_see_it(client: AsyncClient, auth_headers):
    create_sub = await client.post(
        "/api/v1/team/users",
        json={"username": "ownersub", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_sub.status_code == 201

    login_resp = await client.post("/auth/login", json={"username": "ownersub", "password": "pass1234"})
    assert login_resp.status_code == 200
    sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Owned App", "package_name": "com.owned.app"},
        headers=sub_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["owner_user_id"] is not None

    list_resp = await client.get("/api/v1/apps", headers=sub_headers)
    assert list_resp.status_code == 200
    apps = list_resp.json()
    assert any(app["package_name"] == "com.owned.app" for app in apps)
