import pytest


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
