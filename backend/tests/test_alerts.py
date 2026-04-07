from datetime import datetime, timedelta

import pytest

from app.models.alert_rule import AlertRule
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services import alert_service
from app.services import notification_service


async def _seed_domain(async_session):
    account = PlatformAccount(
        platform="namecom",
        account_name="ops",
        credentials="{}",
        is_active=True,
    )
    async_session.add(account)
    await async_session.flush()

    domain = Domain(
        account_id=account.id,
        domain_name="example.com",
        tld="com",
        status="active",
        expiry_date=datetime.utcnow() + timedelta(days=3),
        auto_renew=False,
        locked=True,
        whois_privacy=False,
        nameservers=[],
        raw_data={},
    )
    async_session.add(domain)
    await async_session.commit()


@pytest.mark.asyncio
async def test_scheduled_alert_does_not_mark_triggered_when_delivery_fails(async_session, monkeypatch):
    await _seed_domain(async_session)

    rule = AlertRule(
        name="expiry-feishu",
        rule_type="domain_expiry",
        days_before=7,
        is_enabled=True,
        channels=["feishu"],
        recipients=["https://example.invalid/hook"],
        apply_to_all=True,
        excluded_platforms=[],
        severity="warning",
        schedule={"type": "daily"},
        last_triggered_at=None,
    )
    async_session.add(rule)
    await async_session.commit()

    async def fake_send_feishu(*args, **kwargs):
        return False

    monkeypatch.setattr(alert_service, "send_feishu", fake_send_feishu)

    result = await alert_service.run_scheduled_alerts(async_session)
    await async_session.refresh(rule)

    assert result == {"triggered_rules": 0, "notifications_sent": 0}
    assert rule.last_triggered_at is None


@pytest.mark.asyncio
async def test_manual_alert_check_continues_after_single_rule_exception(async_session, monkeypatch):
    await _seed_domain(async_session)

    bad_rule = AlertRule(
        name="bad-webhook",
        rule_type="domain_expiry",
        days_before=7,
        is_enabled=True,
        channels=["webhook"],
        recipients=["https://example.invalid/fail"],
        apply_to_all=True,
        excluded_platforms=[],
        severity="warning",
        schedule={"type": "manual"},
    )
    good_rule = AlertRule(
        name="good-feishu",
        rule_type="domain_expiry",
        days_before=7,
        is_enabled=True,
        channels=["feishu"],
        recipients=["https://example.invalid/ok"],
        apply_to_all=True,
        excluded_platforms=[],
        severity="warning",
        schedule={"type": "manual"},
    )
    async_session.add_all([bad_rule, good_rule])
    await async_session.commit()

    async def fake_send_webhook(*args, **kwargs):
        raise RuntimeError("webhook down")

    async def fake_send_feishu(*args, **kwargs):
        return True

    monkeypatch.setattr(notification_service, "send_webhook", fake_send_webhook)
    monkeypatch.setattr(alert_service, "send_feishu", fake_send_feishu)

    result = await alert_service.check_expiring_domains(async_session)

    assert result["checked"] is True
    assert result["rules_checked"] == 2
    assert result["notifications_sent"] == 1


@pytest.mark.asyncio
async def test_webhook_payload_serializes_expiry_date(async_session, monkeypatch):
    await _seed_domain(async_session)

    captured = {}
    rule = AlertRule(
        name="webhook-expiry",
        rule_type="domain_expiry",
        days_before=7,
        is_enabled=True,
        channels=["webhook"],
        recipients=["https://example.invalid/hook"],
        apply_to_all=True,
        excluded_platforms=[],
        severity="warning",
        schedule={"type": "manual"},
    )
    async_session.add(rule)
    await async_session.commit()

    async def fake_send_webhook(url, payload):
        captured["payload"] = payload
        return True

    monkeypatch.setattr(notification_service, "send_webhook", fake_send_webhook)

    result = await alert_service.check_expiring_domains(async_session)

    assert result["notifications_sent"] == 1
    assert isinstance(captured["payload"]["domains"][0]["expiry_date"], str)


@pytest.mark.asyncio
async def test_feishu_payload_truncates_long_domain_list(monkeypatch):
    captured = {}

    async def fake_send_webhook(url, payload):
        captured["payload"] = payload
        return True

    monkeypatch.setattr(notification_service, "send_webhook", fake_send_webhook)

    domains = [
        {
            "domain_name": f"example{i}.com",
            "platform": "namecom",
            "expiry_date": datetime.utcnow() + timedelta(days=i + 1),
            "days_left": i + 1,
        }
        for i in range(25)
    ]

    ok = await notification_service.send_feishu(
        "https://example.invalid/hook",
        "Alert",
        domains,
        "warning",
    )

    content = captured["payload"]["card"]["elements"][0]["content"]
    assert ok is True
    assert "example24.com" not in content
    assert "其余 **5** 个域名已省略" in content
