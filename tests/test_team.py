import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_sub_admin_allows_duplicate_email(client: AsyncClient, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Team App", "package_name": "com.team.app"},
        headers=auth_headers,
    )
    app_id = create_app.json()["id"]

    first = await client.post(
        "/api/v1/team/users",
        json={
          "username": "suba",
          "password": "pass1234",
          "email": "shared@test.com",
          "app_ids": [app_id],
        },
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/team/users",
        json={
          "username": "subb",
          "password": "pass1234",
          "email": "shared@test.com",
          "app_ids": [app_id],
        },
        headers=auth_headers,
    )
    assert second.status_code == 201
    assert second.json()["assigned_projects"][0]["name"] == "Team App"


@pytest.mark.asyncio
async def test_create_sub_admin_rejects_duplicate_username(client: AsyncClient, auth_headers):
    first = await client.post(
        "/api/v1/team/users",
        json={"username": "sameuser", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/team/users",
        json={"username": "sameuser", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_sub_admin_disabled_cannot_login(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/team/users",
        json={"username": "disabledsub", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    disable_resp = await client.patch(
        f"/api/v1/team/users/{user_id}/status",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert disable_resp.status_code == 200

    login_resp = await client.post(
        "/auth/login",
        json={"username": "disabledsub", "password": "pass1234"},
    )
    assert login_resp.status_code == 403


@pytest.mark.asyncio
async def test_sub_admin_can_only_see_assigned_apps(client: AsyncClient, auth_headers):
    first_app = await client.post(
        "/api/v1/apps",
        json={"name": "Assigned App", "package_name": "com.assigned.app"},
        headers=auth_headers,
    )
    second_app = await client.post(
        "/api/v1/apps",
        json={"name": "Hidden App", "package_name": "com.hidden.app"},
        headers=auth_headers,
    )
    first_app_id = first_app.json()["id"]

    create_sub = await client.post(
        "/api/v1/team/users",
        json={
          "username": "assignedsub",
          "password": "pass1234",
          "email": "",
          "app_ids": [first_app_id],
        },
        headers=auth_headers,
    )
    assert create_sub.status_code == 201

    login_resp = await client.post(
        "/auth/login",
        json={"username": "assignedsub", "password": "pass1234"},
    )
    token = login_resp.json()["access_token"]
    sub_headers = {"Authorization": f"Bearer {token}"}

    list_apps_resp = await client.get("/api/v1/apps", headers=sub_headers)
    assert list_apps_resp.status_code == 200
    apps = list_apps_resp.json()
    assert len(apps) == 1
    assert apps[0]["package_name"] == "com.assigned.app"


@pytest.mark.asyncio
async def test_delete_sub_admin(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/team/users",
        json={"username": "deleteuser", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/team/users/{user_id}", headers=auth_headers)
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_team_list_shows_owned_and_assigned_projects(client: AsyncClient, auth_headers):
    create_sub = await client.post(
        "/api/v1/team/users",
        json={"username": "projectsub", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_sub.status_code == 201
    user_id = create_sub.json()["id"]

    login_resp = await client.post("/auth/login", json={"username": "projectsub", "password": "pass1234"})
    assert login_resp.status_code == 200
    sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    own_app = await client.post(
        "/api/v1/apps",
        json={"name": "Own Project", "package_name": "com.own.project"},
        headers=sub_headers,
    )
    assigned_app = await client.post(
        "/api/v1/apps",
        json={"name": "Assigned Project", "package_name": "com.assigned.project"},
        headers=auth_headers,
    )
    assert own_app.status_code == 201
    assert assigned_app.status_code == 201

    update_resp = await client.put(
        f"/api/v1/team/users/{user_id}/apps",
        json={"app_ids": [assigned_app.json()["id"]]},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200

    team_resp = await client.get("/api/v1/team/users", headers=auth_headers)
    assert team_resp.status_code == 200
    member = next(item for item in team_resp.json() if item["id"] == user_id)
    assert any(project["name"] == "Assigned Project" for project in member["assigned_projects"])
    assert any(project["name"] == "Own Project" for project in member["owned_projects"])
