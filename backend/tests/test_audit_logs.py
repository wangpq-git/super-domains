from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.schemas.dns_record import DnsRecordCreate
from app.services import audit_log_service, auth_service, dns_service


class DummyAdapter:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def create_dns_record(self, domain_name, record_info):
        return f'{domain_name}-record-id'

    async def update_dns_record(self, domain_name, external_id, record_info):
        return None

    async def delete_dns_record(self, domain_name, external_id):
        return None


@pytest.mark.asyncio
async def test_login_writes_audit_log(client, async_session, sample_user, monkeypatch):
    async def fake_authenticate_user(db, username, password):
        assert username == 'audit_login'
        assert password == 'LoginPass123'
        return sample_user

    monkeypatch.setattr(auth_service, 'authenticate_user', fake_authenticate_user)

    response = await client.post(
        '/api/v1/auth/login',
        json={'username': 'audit_login', 'password': 'LoginPass123'},
    )

    assert response.status_code == 200

    result = await async_session.execute(select(AuditLog).where(AuditLog.action == 'auth.login'))
    log = result.scalar_one()
    assert log.target_type == 'user'
    assert log.detail['username'] == sample_user.username


@pytest.mark.asyncio
async def test_audit_logs_api_supports_domain_scope(client, async_session, sample_user, auth_headers):
    await audit_log_service.add_audit_log(
        async_session,
        user_id=sample_user.id,
        action='platform.sync',
        target_type='platform_account',
        target_id=1,
        detail={'account_name': 'cf-main'},
    )
    await audit_log_service.add_audit_log(
        async_session,
        user_id=sample_user.id,
        action='dns.update',
        target_type='dns_record',
        target_id=2,
        detail={'domain_name': 'example.com'},
    )
    await async_session.commit()

    response = await client.get('/api/v1/audit-logs?scope=domain', headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['action'] == 'dns.update'
    assert data['items'][0]['domain_name'] == 'example.com'


@pytest.mark.asyncio
async def test_create_dns_record_writes_domain_audit_log(async_session, sample_user, monkeypatch):
    account = PlatformAccount(
        platform='cloudflare',
        account_name='cf-audit',
        credentials='{}',
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name='audit-example.com',
        status='active',
        expiry_date=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        nameservers=['ada.ns.cloudflare.com', 'tom.ns.cloudflare.com'],
    )
    async_session.add(domain)
    await async_session.commit()
    await async_session.refresh(domain)

    monkeypatch.setattr(dns_service, 'decrypt_credentials', lambda credentials: {})
    monkeypatch.setattr(dns_service, 'get_adapter', lambda platform, credentials: DummyAdapter())

    record = await dns_service.create_dns_record(
        async_session,
        domain.id,
        DnsRecordCreate(record_type='A', name='@', content='1.1.1.1', ttl=120),
        audit_user_id=sample_user.id,
        audit_context={'mode': 'direct'},
    )

    result = await async_session.execute(select(AuditLog).where(AuditLog.action == 'dns.create'))
    log = result.scalar_one()
    assert record.id == log.target_id
    assert log.detail['domain_name'] == 'audit-example.com'
    assert log.detail['after']['content'] == '1.1.1.1'
    assert log.detail['mode'] == 'direct'
