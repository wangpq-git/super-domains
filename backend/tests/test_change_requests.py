import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.change_request import ChangeRequest
from app.models.dns_record import DnsRecord
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.models.user import User
from app.services import change_request_service, dns_service
from app.services.change_request_service import build_feishu_change_request_card


def _build_feishu_raw_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _sign_feishu_payload(payload: dict, *, timestamp: str, nonce: str, encrypt_key: str) -> str:
    raw_body = _build_feishu_raw_payload(payload)
    string_to_sign = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + raw_body
    return hashlib.sha256(string_to_sign).hexdigest()


@pytest.mark.asyncio
async def test_resolve_admin_user_prefers_email_lookup(async_session):
    user = User(
        username="songxin",
        email="songxin@adsconflux.com",
        password_hash="unused",
        role="admin",
        is_active=True,
    )
    async_session.add(user)
    await async_session.commit()

    approver = await change_request_service.resolve_admin_user(
        async_session,
        {
            "username": "Completely Different Name",
            "email": "songxin@adsconflux.com",
            "open_id": "ou_not_configured",
        },
    )

    assert approver is not None
    assert approver.username == "songxin"


@pytest.mark.asyncio
async def test_resolve_admin_user_supports_email_only_mapping(async_session, monkeypatch):
    user = User(
        username="songxin",
        email="songxin@adsconflux.com",
        password_hash="unused",
        role="admin",
        is_active=True,
    )
    async_session.add(user)
    await async_session.commit()

    async def fake_parse_admin_map(_db):
        return {
            "songxin@adsconflux.com": "songxin",
        }

    monkeypatch.setattr(change_request_service, "_parse_admin_map", fake_parse_admin_map)

    approver = await change_request_service.resolve_admin_user(
        async_session,
        {
            "username": "Wrong Display Name",
            "email": "SongXin@adsconflux.com",
            "open_id": "ou_not_configured",
        },
    )

    assert approver is not None
    assert approver.username == "songxin"



@pytest.mark.asyncio
async def test_create_dns_record_returns_pending_change_request(client, async_session, auth_headers):
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
        domain_name="example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "www",
            "content": "1.2.3.4",
            "ttl": 300,
        },
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["operation_type"] == "dns_create"
    assert data["domain_id"] == domain.id
    assert data["payload"]["data"]["content"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_create_dns_record_rejects_non_cloudflare_domain(client, async_session, auth_headers):
    account = PlatformAccount(
        platform="dynadot",
        account_name="dynadot-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="non-cf.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.dynadot.com", "ns2.dynadot.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "www",
            "content": "1.2.3.4",
            "ttl": 300,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "目前仅支持修改 Cloudflare 平台上的域名"


@pytest.mark.asyncio
async def test_batch_nameserver_request_rejects_non_dynadot_domain(client, async_session, auth_headers):
    account = PlatformAccount(
        platform="namecom",
        account_name="namecom-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="batch-non-cf.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.name.com", "ns2.name.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    resp = await client.post(
        "/api/v1/batch/nameservers",
        headers=auth_headers,
        json={
            "domain_ids": [domain.id],
            "nameservers": ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
        },
    )

    assert resp.status_code == 400
    assert "目前仅支持修改 Dynadot 域名的 NS" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_batch_nameserver_request_creates_pending_request_for_dynadot_domain(client, async_session, auth_headers, monkeypatch):
    account = PlatformAccount(
        platform="dynadot",
        account_name="dynadot-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="pending-ns.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.dynadot.com", "ns2.dynadot.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def require_approval(_db, _user):
        return True

    monkeypatch.setattr(change_request_service, "should_require_approval", require_approval)

    resp = await client.post(
        "/api/v1/batch/nameservers",
        headers=auth_headers,
        json={
            "domain_ids": [domain.id],
            "nameservers": ["olivia.ns.cloudflare.com", "quentin.ns.cloudflare.com"],
        },
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["operation_type"] == "batch_nameserver_update"


@pytest.mark.asyncio
async def test_batch_nameserver_direct_executes_dynadot_update(client, async_session, auth_headers, monkeypatch):
    account = PlatformAccount(
        platform="dynadot",
        account_name="dynadot-test",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="ns-update.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.dynadot.com", "ns2.dynadot.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def skip_approval(_db, _user):
        return False

    class FakeAdapter:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def update_nameservers(self, domain_name, nameservers):
            self.calls.append((domain_name, nameservers))
            return True

    fake_adapter = FakeAdapter()

    monkeypatch.setattr(change_request_service, "should_require_approval", skip_approval)
    monkeypatch.setattr(change_request_service, "decrypt_credentials", lambda value: value)
    monkeypatch.setattr(change_request_service, "get_adapter", lambda platform, credentials: fake_adapter)

    resp = await client.post(
        "/api/v1/batch/nameservers",
        headers=auth_headers,
        json={
            "domain_ids": [domain.id],
            "nameservers": ["olivia.ns.cloudflare.com", "quentin.ns.cloudflare.com"],
        },
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "succeeded"
    assert fake_adapter.calls == [
        ("ns-update.example.com", ["olivia.ns.cloudflare.com", "quentin.ns.cloudflare.com"])
    ]

    await async_session.refresh(domain)
    assert domain.nameservers == ["olivia.ns.cloudflare.com", "quentin.ns.cloudflare.com"]


@pytest.mark.asyncio
async def test_cloudflare_onboard_request_selects_least_loaded_available_account(client, async_session, auth_headers):
    source_account = PlatformAccount(
        platform="dynadot",
        account_name="dynadot-source",
        credentials="{}",
        is_active=True,
    )
    cf_busy = PlatformAccount(
        platform="cloudflare",
        account_name="cf-busy",
        credentials="{}",
        is_active=True,
    )
    cf_best = PlatformAccount(
        platform="cloudflare",
        account_name="cf-best",
        credentials="{}",
        is_active=True,
    )
    async_session.add_all([source_account, cf_busy, cf_best])
    await async_session.flush()

    source_domain = Domain(
        account_id=source_account.id,
        domain_name="migrate.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.dynadot.com", "ns2.dynadot.com"],
    )
    async_session.add(source_domain)

    for idx in range(3):
        async_session.add(
            Domain(
                account_id=cf_busy.id,
                domain_name=f"busy-{idx}.example.com",
                status="active",
                expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
                nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
            )
        )

    async_session.add(
        Domain(
            account_id=cf_best.id,
            domain_name="best-0.example.com",
            status="active",
            expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
            nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
        )
    )

    await async_session.commit()
    await async_session.refresh(source_domain)

    resp = await client.post(
        f"/api/v1/domains/{source_domain.id}/onboard-cloudflare",
        headers=auth_headers,
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["operation_type"] == "cloudflare_onboard"
    assert data["payload"]["target_account_id"] == cf_best.id
    assert data["payload"]["target_account_name"] == "cf-best"
    assert data["payload"]["default_proxied"] is True
    assert data["payload"]["cache_rule"]["expression"]


@pytest.mark.asyncio
async def test_cloudflare_onboard_direct_executes_zone_creation_cache_rule_and_ns_update(client, async_session, auth_headers, monkeypatch):
    source_account = PlatformAccount(
        platform="dynadot",
        account_name="dynadot-source",
        credentials="{}",
        is_active=True,
    )
    target_account = PlatformAccount(
        platform="cloudflare",
        account_name="cf-target",
        credentials="{}",
        is_active=True,
    )
    async_session.add_all([source_account, target_account])
    await async_session.flush()

    source_domain = Domain(
        account_id=source_account.id,
        domain_name="direct-migrate.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["ns1.dynadot.com", "ns2.dynadot.com"],
    )
    async_session.add(source_domain)
    await async_session.commit()
    await async_session.refresh(source_domain)

    async def skip_approval(_db, _user):
        return False

    class FakeDynadotAdapter:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def update_nameservers(self, domain_name, nameservers):
            self.calls.append((domain_name, nameservers))
            return True

    class FakeCloudflareAdapter:
        def __init__(self):
            self.zone_calls = []
            self.cache_calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def create_zone(self, domain_name):
            self.zone_calls.append(domain_name)
            return {
                "zone_id": "zone-123",
                "status": "pending",
                "nameservers": ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
                "zone": {"id": "zone-123", "name": domain_name, "status": "pending"},
            }

        async def ensure_cache_rule(self, domain_name, *, expression, description):
            self.cache_calls.append((domain_name, expression, description))
            return {"rule_id": "rule-1", "ruleset_id": "ruleset-1", "created": True}

    fake_dynadot = FakeDynadotAdapter()
    fake_cloudflare = FakeCloudflareAdapter()

    def fake_get_adapter(platform, _credentials):
        if platform == "dynadot":
            return fake_dynadot
        if platform == "cloudflare":
            return fake_cloudflare
        raise AssertionError(f"unexpected platform {platform}")

    monkeypatch.setattr(change_request_service, "should_require_approval", skip_approval)
    monkeypatch.setattr(change_request_service, "decrypt_credentials", lambda value: value)
    monkeypatch.setattr(change_request_service, "get_adapter", fake_get_adapter)

    resp = await client.post(
        f"/api/v1/domains/{source_domain.id}/onboard-cloudflare",
        headers=auth_headers,
    )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "succeeded"
    assert data["operation_type"] == "cloudflare_onboard"
    assert data["execution_result"]["target_account_id"] == target_account.id
    assert data["execution_result"]["nameservers"] == ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"]
    assert fake_cloudflare.zone_calls == ["direct-migrate.example.com"]
    assert fake_dynadot.calls == [
        ("direct-migrate.example.com", ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"])
    ]

    await async_session.refresh(source_domain)
    assert source_domain.nameservers == ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"]

    result = await async_session.execute(
        select(Domain).where(Domain.account_id == target_account.id, Domain.domain_name == "direct-migrate.example.com")
    )
    cf_domain = result.scalar_one()
    assert cf_domain.external_id == "zone-123"
    assert cf_domain.nameservers == ["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"]


@pytest.mark.asyncio
async def test_list_change_requests_supports_filters_and_pagination(client, async_session, auth_headers):
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
        domain_name="filter.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    for idx in range(3):
        await client.post(
            f"/api/v1/dns/{domain.id}/records",
            headers=auth_headers,
            json={
                "record_type": "A",
                "name": f"www-{idx}",
                "content": f"1.2.3.{idx}",
                "ttl": 300,
            },
        )

    resp = await client.get(
        "/api/v1/change-requests",
        headers=auth_headers,
        params={"page": 1, "page_size": 2, "status": "pending_approval", "operation_type": "dns_create"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    assert all(item["status"] == "pending_approval" for item in data["items"])
    assert all(item["operation_type"] == "dns_create" for item in data["items"])


@pytest.mark.asyncio
async def test_approve_change_request_executes_dns_create(client, async_session, auth_headers, monkeypatch):
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
        domain_name="example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=321)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "5.6.7.8",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    approve_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )

    assert approve_resp.status_code == 200
    data = approve_resp.json()
    assert data["status"] == "succeeded"
    assert data["execution_result"]["record_id"] == 321
    assert data["approver_user_id"] is not None


@pytest.mark.asyncio
async def test_feishu_callback_approve_executes_request(client, async_session, auth_headers, sample_user, monkeypatch):
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
        domain_name="callback.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=654)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.9",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "operator": {
                    "username": sample_user.username,
                },
                "action": {
                    "value": {
                        "action": "approve",
                        "request_id": str(request_id),
                    }
                }
            },
        },
    )

    assert callback_resp.status_code == 200
    data = callback_resp.json()
    assert data["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in data["card"]["data"]["elements"])


@pytest.mark.asyncio
async def test_feishu_callback_reject_marks_request_rejected(client, async_session, auth_headers, sample_user, monkeypatch):
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
        domain_name="reject.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.9",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "operator": {
                    "username": sample_user.username,
                },
                "action": {
                    "value": {
                        "action": "reject",
                        "request_id": str(request_id),
                        "reason": "not allowed",
                    }
                }
            },
        },
    )

    assert callback_resp.status_code == 200
    data = callback_resp.json()
    assert data["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in data["card"]["data"]["elements"])
    assert any(element["tag"] == "note" for element in data["card"]["data"]["elements"])


@pytest.mark.asyncio
async def test_feishu_callback_requires_real_operator_identity(client, async_session, auth_headers, sample_user, monkeypatch):
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
        domain_name="strict-identity.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=755)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.5",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "action": {
                    "value": {
                        "action": "approve",
                        "request_id": str(request_id),
                        "approver_user_id": str(sample_user.id),
                    }
                }
            },
        },
    )

    assert callback_resp.status_code == 200
    data = callback_resp.json()
    assert data["toast"]["type"] == "error"
    assert data["toast"]["content"] == "审批人未授权"

    result = await async_session.execute(select(ChangeRequest).where(ChangeRequest.id == request_id))
    change_request = result.scalar_one()
    assert change_request.status == "pending_approval"


@pytest.mark.asyncio
async def test_feishu_callback_approve_resolves_operator_username(client, async_session, auth_headers, monkeypatch):
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
        domain_name="operator.example.com",
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
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.8",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {
                "username": "testadmin",
            },
            "action": {
                "value": {
                    "action": "approve",
                    "request_id": str(request_id),
                }
            },
        },
    }

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json=payload,
    )

    assert callback_resp.status_code == 200
    data = callback_resp.json()
    assert data["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in data["card"]["data"]["elements"])


@pytest.mark.asyncio
async def test_feishu_callback_validates_signature(client, async_session, auth_headers, monkeypatch):
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
        domain_name="signed.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=888)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_ENCRYPT_KEY", "enc-key-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS", 300)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.7",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {
                "username": "testadmin",
            },
            "action": {
                "value": {
                    "action": "approve",
                    "request_id": str(request_id),
                }
            },
        },
    }
    timestamp = str(int(time.time()))
    nonce = "nonce-123"
    signature = _sign_feishu_payload(payload, timestamp=timestamp, nonce=nonce, encrypt_key="enc-key-123")

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={
            "Content-Type": "application/json",
            "X-Feishu-Token": "token-123",
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        },
        content=_build_feishu_raw_payload(payload),
    )

    assert callback_resp.status_code == 200
    assert all(element["tag"] != "action" for element in callback_resp.json()["card"]["data"]["elements"])


@pytest.mark.asyncio
async def test_feishu_callback_accepts_invalid_signature_after_payload_validation(
    client, async_session, auth_headers, monkeypatch
):
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
        domain_name="invalid-sign.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=1006)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_ENCRYPT_KEY", "enc-key-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_SIGNATURE_TOLERANCE_SECONDS", 300)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "cb",
            "content": "9.9.9.6",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {
                "username": "testadmin",
            },
            "action": {
                "value": {
                    "action": "approve",
                    "request_id": str(request_id),
                }
            },
        },
    }

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={
            "X-Feishu-Token": "token-123",
            "X-Lark-Request-Timestamp": str(int(time.time())),
            "X-Lark-Request-Nonce": "nonce-123",
            "X-Lark-Signature": "invalid-signature",
        },
        json=payload,
    )

    assert callback_resp.status_code == 200
    assert callback_resp.json()["toast"]["type"] == "success"


@pytest.mark.asyncio
async def test_approve_change_request_sends_result_notification(client, async_session, auth_headers, monkeypatch):
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
        domain_name="notify-success.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    sent_payloads = []

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=999)

    async def fake_send_webhook(url, payload):
        sent_payloads.append((url, payload))
        return True

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.services.change_request_service.send_webhook", fake_send_webhook)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "1.1.1.1",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    approve_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )

    assert approve_resp.status_code == 200
    assert len(sent_payloads) == 2
    result_payload = sent_payloads[-1][1]
    result_text = "\n".join(
        element["text"]["content"]
        for element in result_payload["card"]["elements"]
        if element["tag"] == "div" and "text" in element
    )
    assert "审批通过" in result_text


@pytest.mark.asyncio
async def test_reject_change_request_sends_result_notification(client, async_session, auth_headers, monkeypatch):
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
        domain_name="notify-reject.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    sent_payloads = []

    async def fake_send_webhook(url, payload):
        sent_payloads.append((url, payload))
        return True

    monkeypatch.setattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.services.change_request_service.send_webhook", fake_send_webhook)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "2.2.2.2",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    reject_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/reject",
        headers=auth_headers,
        json={"reason": "manual reject"},
    )

    assert reject_resp.status_code == 200
    assert len(sent_payloads) == 2
    result_payload = sent_payloads[-1][1]
    result_text = "\n".join(
        element["text"]["content"]
        for element in result_payload["card"]["elements"]
        if element["tag"] == "div" and "text" in element
    )
    assert "manual reject" in result_text


@pytest.mark.asyncio
async def test_repeat_approve_api_is_idempotent(client, async_session, auth_headers, monkeypatch):
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
        domain_name="repeat-api.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    call_count = 0

    async def fake_create_dns_record(db, domain_id, data):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(id=1001)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "3.3.3.3",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    first_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )
    second_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    assert second_resp.json()["status"] == "succeeded"
    assert call_count == 1


@pytest.mark.asyncio
async def test_repeat_feishu_callback_is_idempotent(client, async_session, auth_headers, monkeypatch):
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
        domain_name="repeat-callback.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    call_count = 0
    sent_payloads = []

    async def fake_create_dns_record(db, domain_id, data):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(id=1002)

    async def fake_send_webhook(url, payload):
        sent_payloads.append((url, payload))
        return True

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.services.change_request_service.send_webhook", fake_send_webhook)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "4.4.4.4",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {
                "username": "testadmin",
            },
            "action": {
                "value": {
                    "action": "approve",
                    "request_id": str(request_id),
                }
            },
        },
    }

    first_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json=payload,
    )
    second_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json=payload,
    )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    assert second_resp.json()["toast"]["type"] == "info"
    assert all(element["tag"] != "action" for element in second_resp.json()["card"]["data"]["elements"])
    assert call_count == 1
    assert len(sent_payloads) == 1


@pytest.mark.asyncio
async def test_feishu_callback_updates_card_without_sending_extra_result_notification(
    client,
    async_session,
    auth_headers,
    monkeypatch,
):
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
        domain_name="callback-no-extra-message.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    sent_payloads = []

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=1003)

    async def fake_send_webhook(url, payload):
        sent_payloads.append((url, payload))
        return True

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.services.change_request_service.send_webhook", fake_send_webhook)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "5.5.5.5",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "operator": {
                    "username": "testadmin",
                },
                "action": {
                    "value": {
                        "action": "approve",
                        "request_id": str(request_id),
                    }
                },
            },
        },
    )

    assert callback_resp.status_code == 200
    assert callback_resp.json()["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in callback_resp.json()["card"]["data"]["elements"])
    assert len(sent_payloads) == 1


@pytest.mark.asyncio
async def test_feishu_callback_returns_updated_card_even_when_bot_message_update_succeeds(
    client,
    async_session,
    auth_headers,
    monkeypatch,
):
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
        domain_name="callback-inline-update.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    update_calls = []

    async def fake_create_dns_record(db, domain_id, data):
        return SimpleNamespace(id=1004)

    async def fake_update_message(**kwargs):
        update_calls.append(kwargs)
        return True

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_BOT_APP_ID", "app-id")
    monkeypatch.setattr(settings, "FEISHU_BOT_APP_SECRET", "app-secret")
    monkeypatch.setattr(
        "app.services.notification_service.update_feishu_bot_interactive_message",
        fake_update_message,
    )

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "5.5.5.5",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    result = await async_session.execute(select(ChangeRequest).where(ChangeRequest.id == request_id))
    change_request = result.scalar_one()
    change_request.payload = {
        **(change_request.payload or {}),
        "feishu_message_id": "om_stored_message_id",
    }
    await async_session.commit()

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "context": {
                    "open_message_id": "om_callback_message_id",
                },
                "operator": {
                    "username": "testadmin",
                },
                "action": {
                    "value": {
                        "action": "approve",
                        "request_id": str(request_id),
                    }
                },
            },
        },
    )

    assert callback_resp.status_code == 200
    assert callback_resp.json()["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in callback_resp.json()["card"]["data"]["elements"])
    assert len(update_calls) == 1
    assert update_calls[0]["message_id"] == "om_stored_message_id"


@pytest.mark.asyncio
async def test_feishu_reject_callback_returns_updated_card_when_bot_message_update_succeeds(
    client,
    async_session,
    auth_headers,
    monkeypatch,
):
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
        domain_name="callback-inline-reject.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    update_calls = []

    async def fake_update_message(**kwargs):
        update_calls.append(kwargs)
        return True

    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_BOT_APP_ID", "app-id")
    monkeypatch.setattr(settings, "FEISHU_BOT_APP_SECRET", "app-secret")
    monkeypatch.setattr(
        "app.services.notification_service.update_feishu_bot_interactive_message",
        fake_update_message,
    )

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "8.8.8.8",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    result = await async_session.execute(select(ChangeRequest).where(ChangeRequest.id == request_id))
    change_request = result.scalar_one()
    change_request.payload = {
        **(change_request.payload or {}),
        "feishu_message_id": "om_reject_message_id",
    }
    await async_session.commit()

    callback_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json={
            "header": {
                "event_type": "card.action.trigger",
                "token": "token-123",
            },
            "event": {
                "operator": {
                    "username": "testadmin",
                },
                "action": {
                    "value": {
                        "action": "reject",
                        "request_id": str(request_id),
                        "reason": "manual reject",
                    }
                },
            },
        },
    )

    assert callback_resp.status_code == 200
    assert callback_resp.json()["toast"]["type"] == "success"
    assert all(element["tag"] != "action" for element in callback_resp.json()["card"]["data"]["elements"])
    assert len(update_calls) == 1
    assert "拒绝" in json.dumps(callback_resp.json()["card"]["data"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_approve_then_reject_keeps_terminal_status(client, async_session, auth_headers, monkeypatch):
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
        domain_name="approve-then-reject.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    call_count = 0

    async def fake_create_dns_record(db, domain_id, data):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(id=1003)

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "5.5.5.5",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    approve_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )
    reject_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/reject",
        headers=auth_headers,
        json={"reason": "too late"},
    )

    assert approve_resp.status_code == 200
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "succeeded"
    assert call_count == 1


@pytest.mark.asyncio
async def test_reject_then_approve_keeps_terminal_status(client, async_session, auth_headers):
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
        domain_name="reject-then-approve.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "6.6.6.6",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    reject_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/reject",
        headers=auth_headers,
        json={"reason": "manual reject"},
    )
    approve_resp = await client.post(
        f"/api/v1/change-requests/{request_id}/approve",
        headers=auth_headers,
    )

    assert reject_resp.status_code == 200
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "rejected"
    assert approve_resp.json()["rejection_reason"] == "manual reject"


@pytest.mark.asyncio
async def test_feishu_reject_after_approve_returns_idempotent_state(client, async_session, auth_headers, monkeypatch):
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
        domain_name="feishu-approve-then-reject.example.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    call_count = 0
    sent_payloads = []

    async def fake_create_dns_record(db, domain_id, data):
        nonlocal call_count
        call_count += 1
        return SimpleNamespace(id=1005)

    async def fake_send_webhook(url, payload):
        sent_payloads.append((url, payload))
        return True

    monkeypatch.setattr(dns_service, "create_dns_record", fake_create_dns_record)
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.services.change_request_service.send_webhook", fake_send_webhook)

    create_resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "A",
            "name": "api",
            "content": "7.7.7.7",
            "ttl": 120,
        },
    )
    request_id = create_resp.json()["id"]

    approve_payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {"username": "testadmin"},
            "action": {"value": {"action": "approve", "request_id": str(request_id)}},
        },
    }
    reject_payload = {
        "header": {
            "event_type": "card.action.trigger",
            "token": "token-123",
        },
        "event": {
            "operator": {"username": "testadmin"},
            "action": {
                "value": {
                    "action": "reject",
                    "request_id": str(request_id),
                    "reason": "late reject",
                }
            },
        },
    }

    approve_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json=approve_payload,
    )
    reject_resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        headers={"X-Feishu-Token": "token-123"},
        json=reject_payload,
    )

    assert approve_resp.status_code == 200
    assert reject_resp.status_code == 200
    assert reject_resp.json()["toast"]["type"] == "info"
    assert all(element["tag"] != "action" for element in reject_resp.json()["card"]["data"]["elements"])
    assert call_count == 1
    assert len(sent_payloads) == 1


@pytest.mark.asyncio
async def test_feishu_callback_challenge_echoes_back(client):
    resp = await client.post(
        "/api/v1/webhooks/feishu/change-requests",
        json={"challenge": "abc123"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


@pytest.mark.asyncio
async def test_update_request_card_uses_before_snapshot_details(client, async_session, auth_headers):
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
        domain_name="ireadpro.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.flush()

    record = DnsRecord(
        domain_id=domain.id,
        record_type="TXT",
        name="test",
        content="old-value",
        ttl=3600,
        sync_status="synced",
    )
    async_session.add(record)
    await async_session.commit()
    await async_session.refresh(record)

    resp = await client.put(
        f"/api/v1/dns/records/{record.id}",
        headers=auth_headers,
        json={"content": "aaaaa"},
    )

    assert resp.status_code == 202
    payload = resp.json()
    change_request = await async_session.get(ChangeRequest, payload["id"])
    card = build_feishu_change_request_card(change_request)
    card_dump = json.dumps(card, ensure_ascii=False)
    assert "TXT" in card_dump
    assert "test" in card_dump
    assert "aaaaa" in card_dump
    assert "3600" in card_dump


@pytest.mark.asyncio
async def test_delete_request_card_uses_before_snapshot_details(client, async_session, auth_headers):
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
        domain_name="ireadpro.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.flush()

    record = DnsRecord(
        domain_id=domain.id,
        record_type="TXT",
        name="test",
        content="test-value",
        ttl=3600,
        sync_status="synced",
    )
    async_session.add(record)
    await async_session.commit()
    await async_session.refresh(record)

    resp = await client.delete(
        f"/api/v1/dns/records/{record.id}",
        headers=auth_headers,
    )

    assert resp.status_code == 202
    payload = resp.json()
    change_request = await async_session.get(ChangeRequest, payload["id"])
    card = build_feishu_change_request_card(change_request)
    card_dump = json.dumps(card, ensure_ascii=False)
    assert "TXT" in card_dump
    assert "test" in card_dump
    assert "test-value" in card_dump
    assert "3600" in card_dump


@pytest.mark.asyncio
async def test_change_request_card_uses_plain_text_sections_for_better_feishu_layout(
    client, async_session, auth_headers
):
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
        domain_name="ireadpro.com",
        status="active",
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=["amy.ns.cloudflare.com", "hugh.ns.cloudflare.com"],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    resp = await client.post(
        f"/api/v1/dns/{domain.id}/records",
        headers=auth_headers,
        json={
            "record_type": "TXT",
            "name": "aaa",
            "content": "aaa",
            "ttl": 3600,
        },
    )

    assert resp.status_code == 202
    change_request = await async_session.get(ChangeRequest, resp.json()["id"])
    card = build_feishu_change_request_card(change_request)

    first_block = card["elements"][0]
    assert first_block["tag"] == "div"
    assert first_block["text"]["tag"] == "plain_text"
    assert "`" not in first_block["text"]["content"]

    field_block = card["elements"][2]
    assert field_block["tag"] == "div"
    assert all(field["text"]["tag"] == "plain_text" for field in field_block["fields"])
