from datetime import datetime, timezone

from app.models.system_log import SystemLog


async def test_admin_can_clear_logs(client, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Logs App", "package_name": "com.logs.app"},
        headers=auth_headers,
    )
    assert create_app.status_code == 201
    app_id = create_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        session.add(
            SystemLog(
                level="info",
                module="test_module",
                message="test log",
                details="{}",
                app_id=app_id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await session.commit()

    before = await client.get(f"/api/v1/logs?app_id={app_id}", headers=auth_headers)
    assert before.status_code == 200
    assert len(before.json()) >= 1

    clear = await client.delete(f"/api/v1/logs?app_id={app_id}", headers=auth_headers)
    assert clear.status_code == 200
    assert clear.json()["status"] == "ok"

    after = await client.get(f"/api/v1/logs?app_id={app_id}", headers=auth_headers)
    assert after.status_code == 200
    assert after.json() == []


async def test_sub_admin_cannot_clear_logs_for_unassigned_app(client, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Hidden Logs App", "package_name": "com.hidden.logs"},
        headers=auth_headers,
    )
    assert create_app.status_code == 201
    hidden_app_id = create_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        session.add(
            SystemLog(
                level="warning",
                module="test_module",
                message="hidden app log",
                details="{}",
                app_id=hidden_app_id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await session.commit()

    create_sub = await client.post(
        "/api/v1/team/users",
        json={"username": "logsub", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_sub.status_code == 201

    login_resp = await client.post("/auth/login", json={"username": "logsub", "password": "pass1234"})
    assert login_resp.status_code == 200
    sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    response = await client.delete(f"/api/v1/logs?app_id={hidden_app_id}", headers=sub_headers)
    assert response.status_code == 403


async def test_sub_admin_can_clear_own_app_logs(client, auth_headers):
    create_sub = await client.post(
        "/api/v1/team/users",
        json={"username": "logowner", "password": "pass1234", "email": "", "app_ids": []},
        headers=auth_headers,
    )
    assert create_sub.status_code == 201

    login_resp = await client.post("/auth/login", json={"username": "logowner", "password": "pass1234"})
    assert login_resp.status_code == 200
    sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    own_app = await client.post(
        "/api/v1/apps",
        json={"name": "Own Logs App", "package_name": "com.own.logs"},
        headers=sub_headers,
    )
    assert own_app.status_code == 201
    own_app_id = own_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        session.add(
            SystemLog(
                level="info",
                module="test_module",
                message="own app log",
                details="{}",
                app_id=own_app_id,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
        await session.commit()

    clear = await client.delete(f"/api/v1/logs?app_id={own_app_id}", headers=sub_headers)
    assert clear.status_code == 200
    assert clear.json()["status"] == "ok"
