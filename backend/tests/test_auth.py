import pytest


@pytest.mark.asyncio
async def test_register_first_user(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "admin", "password": "Admin123456"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_login(client):
    await client.post(
        "/api/v1/auth/register",
        json={"username": "logintest", "password": "LoginPass123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "logintest", "password": "LoginPass123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/api/v1/auth/register",
        json={"username": "wrongpasstest", "password": "CorrectPass123"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "wrongpasstest", "password": "BadPassword999"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, sample_user, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_user.id
    assert data["username"] == sample_user.username
    assert data["role"] == sample_user.role
