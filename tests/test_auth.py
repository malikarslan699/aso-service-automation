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
