import pytest
from httpx import AsyncClient


async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_login_success(client: AsyncClient, admin_user):
    response = await client.post("/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"


async def test_login_wrong_password(client: AsyncClient, admin_user):
    response = await client.post("/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert response.status_code == 401


async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post("/auth/login", json={"username": "nobody", "password": "pass"})
    assert response.status_code == 401


async def test_login_rate_limited_after_too_many_failures(client: AsyncClient, admin_user):
    headers = {"X-Forwarded-For": "203.0.113.10"}

    for _ in range(10):
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "wrong"},
            headers=headers,
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/auth/login",
        json={"username": "testadmin", "password": "wrong"},
        headers=headers,
    )
    assert blocked.status_code == 429


async def test_login_success_resets_failed_attempt_counter(client: AsyncClient, admin_user):
    headers = {"X-Forwarded-For": "203.0.113.11"}

    for _ in range(5):
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "wrong"},
            headers=headers,
        )
        assert response.status_code == 401

    success = await client.post(
        "/auth/login",
        json={"username": "testadmin", "password": "testpass"},
        headers=headers,
    )
    assert success.status_code == 200

    for _ in range(10):
        response = await client.post(
            "/auth/login",
            json={"username": "testadmin", "password": "wrong"},
            headers=headers,
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/auth/login",
        json={"username": "testadmin", "password": "wrong"},
        headers=headers,
    )
    assert blocked.status_code == 429


async def test_me_endpoint(client: AsyncClient, admin_user):
    """Login first, then use the returned token for /me."""
    login_resp = await client.post("/auth/login", json={"username": "testadmin", "password": "testpass"})
    token = login_resp.json()["access_token"]
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testadmin"
    assert data["role"] == "admin"


async def test_me_no_token(client: AsyncClient):
    response = await client.get("/auth/me")
    assert response.status_code == 403  # HTTPBearer returns 403 when no credentials
