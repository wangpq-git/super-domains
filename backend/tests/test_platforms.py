import pytest
from datetime import datetime

from app.models.domain import Domain


@pytest.mark.asyncio
async def test_create_account(client, auth_headers):
    resp = await client.post(
        "/api/v1/platforms",
        json={
            "platform": "cloudflare",
            "account_name": "test-cf",
            "credentials": {"api_token": "test_token_123"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["platform"] == "cloudflare"
    assert data["account_name"] == "test-cf"
    assert data["is_active"] is True
    assert data["sync_status"] == "idle"


@pytest.mark.asyncio
async def test_list_accounts(client, auth_headers):
    await client.post(
        "/api/v1/platforms",
        json={
            "platform": "cloudflare",
            "credentials": {"api_token": "tok1"},
        },
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/platforms",
        json={
            "platform": "namecom",
            "credentials": {"username": "user", "api_token": "tok2"},
        },
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/platforms")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 2
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_update_account(client, auth_headers):
    create_resp = await client.post(
        "/api/v1/platforms",
        json={
            "platform": "cloudflare",
            "account_name": "original-name",
            "credentials": {"api_token": "old_token"},
        },
        headers=auth_headers,
    )
    account_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/platforms/{account_id}",
        json={"account_name": "updated-name"},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["account_name"] == "updated-name"


@pytest.mark.asyncio
async def test_update_account_returns_domain_count_without_lazy_load(client, auth_headers, async_session):
    create_resp = await client.post(
        "/api/v1/platforms",
        json={
            "platform": "dynadot",
            "account_name": "sync-test",
            "credentials": {"api_key": "old-key"},
        },
        headers=auth_headers,
    )
    account_id = create_resp.json()["id"]

    async_session.add(
        Domain(
            account_id=account_id,
            domain_name="example.com",
            tld="com",
            status="active",
            expiry_date=datetime(2030, 1, 1),
        )
    )
    await async_session.commit()

    update_resp = await client.put(
        f"/api/v1/platforms/{account_id}",
        json={"credentials": {"api_key": "new-key"}},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["domain_count"] == 1


@pytest.mark.asyncio
async def test_delete_account(client, auth_headers):
    create_resp = await client.post(
        "/api/v1/platforms",
        json={
            "platform": "cloudflare",
            "credentials": {"api_token": "del_token"},
        },
        headers=auth_headers,
    )
    account_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/platforms/{account_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/platforms/{account_id}")
    assert get_resp.status_code == 404
