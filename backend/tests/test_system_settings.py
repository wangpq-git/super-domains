from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services import dns_service


@pytest.mark.asyncio
async def test_system_settings_list_and_update_mask_secret(client, auth_headers):
    save_resp = await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "APPROVAL_ENABLED", "value": True},
                {"key": "FEISHU_APPROVAL_WEBHOOK_URL", "value": "https://example.com/hook/secret-token"},
                {"key": "LDAP_HOST", "value": "ldap.example.com"},
            ]
        },
    )

    assert save_resp.status_code == 200
    saved = {item["key"]: item for item in save_resp.json()["items"]}
    assert saved["APPROVAL_ENABLED"]["value"] is True
    assert saved["FEISHU_APPROVAL_WEBHOOK_URL"]["value"] is None
    assert saved["FEISHU_APPROVAL_WEBHOOK_URL"]["masked_value"]
    assert saved["LDAP_HOST"]["value"] == "ldap.example.com"

    list_resp = await client.get("/api/v1/system-settings", headers=auth_headers)
    assert list_resp.status_code == 200
    listed = {item["key"]: item for item in list_resp.json()["items"]}
    assert listed["FEISHU_APPROVAL_WEBHOOK_URL"]["source"] == "database"
    assert listed["FEISHU_APPROVAL_WEBHOOK_URL"]["masked_value"]


@pytest.mark.asyncio
async def test_feishu_callback_uses_database_config(client, async_session, auth_headers, monkeypatch):
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
        domain_name="db-config.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=777)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)

    config_resp = await client.put(
        "/api/v1/system-settings",
        headers=auth_headers,
        json={
            "items": [
                {"key": "FEISHU_APPROVAL_CALLBACK_TOKEN", "value": "db-token"},
                {"key": "APPROVAL_ENABLED", "value": True},
            ]
        },
    )
    assert config_resp.status_code == 200

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "1.1.1.1",
            "ttl": 120,
        },
    )
    assert create_resp.status_code == 202
    request_id = create_resp.json()["id"]

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "db-token"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "db-token",
            },
            "event": {
                "action": {
                    "value": {
                        "action": "approve",
                        "request_id": str(request_id),
                    }
                },
                "operator": {
                    "username": "testadmin",
                },
            },
        },
    )

    assert callback_resp.status_code == 200
    payload = callback_resp.json()
    assert payload["status"] == "succeeded"
    assert payload["approver_user_id"] is not None
