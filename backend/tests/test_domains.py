from datetime import datetime, timedelta

import pytest

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount


@pytest.mark.asyncio
async def test_list_domains_empty(client):
    resp = await client.get("/api/v1/domains")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_domain_stats(client):
    resp = await client.get("/api/v1/domains/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_domains" in data
    assert "by_platform" in data
    assert "by_status" in data
    assert "expiring_30d" in data
    assert "expiring_7d" in data
    assert "expired" in data
    assert data["total_domains"] == 0


@pytest.mark.asyncio
async def test_list_domains_for_dns_manage_filters_manageable_non_expired(client, async_session):
    account = PlatformAccount(
        platform="cloudflare",
        account_name="cf-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    now = datetime.utcnow()
    async_session.add_all([
        Domain(
            account_id=account.id,
            domain_name="managed.example",
            status="active",
            expiry_date=now + timedelta(days=10),
            nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
        ),
        Domain(
            account_id=account.id,
            domain_name="expired.example",
            status="active",
            expiry_date=now - timedelta(days=1),
            nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
        ),
        Domain(
            account_id=account.id,
            domain_name="external.example",
            status="active",
            expiry_date=now + timedelta(days=10),
            nameservers=["ns1.example.com", "ns2.example.com"],
        ),
    ])
    await async_session.commit()

    resp = await client.get(
        "/api/v1/domains",
        params={"exclude_expired": "true", "dns_manageable_only": "true"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert [item["domain_name"] for item in data["items"]] == ["managed.example"]
