from datetime import UTC, datetime, timedelta

import pytest

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount


@pytest.mark.asyncio
async def test_sync_dns_records_skips_unmanaged_domain(client, async_session):
    account = PlatformAccount(
        platform="cloudflare",
        account_name="cf-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="external.example",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        nameservers=["ns1.example.com", "ns2.example.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    resp = await client.post(f"/api/v1/dns/{domain.id}/sync")

    assert resp.status_code == 200
    assert resp.json()["error"] == "当前域名未过期，但 NS 不在当前账户下，已跳过同步"
