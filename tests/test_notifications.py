import pytest

from app.models.notification import Notification


@pytest.mark.asyncio
async def test_notifications_app_id_optional_lists_accessible_apps(client, auth_headers):
    first_app = await client.post(
        "/api/v1/apps",
        json={"name": "Notif App A", "package_name": "com.notif.a"},
        headers=auth_headers,
    )
    second_app = await client.post(
        "/api/v1/apps",
        json={"name": "Notif App B", "package_name": "com.notif.b"},
        headers=auth_headers,
    )
    assert first_app.status_code == 201
    assert second_app.status_code == 201

    from tests.conftest import test_session

    async with test_session() as session:
        session.add(
            Notification(
                app_id=first_app.json()["id"],
                title="A1",
                message="First app notification",
                notification_type="info",
            )
        )
        session.add(
            Notification(
                app_id=second_app.json()["id"],
                title="B1",
                message="Second app notification",
                notification_type="warning",
            )
        )
        await session.commit()

    all_resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert len(all_data) >= 2
    assert {item["app_id"] for item in all_data}.issuperset({first_app.json()["id"], second_app.json()["id"]})

    scoped_resp = await client.get(
        f"/api/v1/notifications?app_id={first_app.json()['id']}",
        headers=auth_headers,
    )
    assert scoped_resp.status_code == 200
    scoped_data = scoped_resp.json()
    assert all(item["app_id"] == first_app.json()["id"] for item in scoped_data)


@pytest.mark.asyncio
async def test_mark_notification_read_without_app_id(client, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Notif Read App", "package_name": "com.notif.read"},
        headers=auth_headers,
    )
    assert create_app.status_code == 201
    app_id = create_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        note = Notification(
            app_id=app_id,
            title="Read me",
            message="Unread",
            notification_type="info",
            is_read=False,
        )
        session.add(note)
        await session.commit()
        notification_id = note.id

    mark_resp = await client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=auth_headers,
    )
    assert mark_resp.status_code == 200

    async with test_session() as session:
        saved = await session.get(Notification, notification_id)
        assert saved is not None
        assert saved.is_read is True


@pytest.mark.asyncio
async def test_notifications_page_limit_returns_envelope(client, auth_headers):
    create_app = await client.post(
        "/api/v1/apps",
        json={"name": "Notif Paging App", "package_name": "com.notif.page"},
        headers=auth_headers,
    )
    assert create_app.status_code == 201
    app_id = create_app.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        for idx in range(3):
            session.add(
                Notification(
                    app_id=app_id,
                    title=f"N{idx}",
                    message="Pagination test",
                    notification_type="info",
                )
            )
        await session.commit()

    resp = await client.get(f"/api/v1/notifications?app_id={app_id}&page=2&limit=2", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 2
    assert data["limit"] == 2
    assert data["total"] == 3
    assert len(data["items"]) == 1
