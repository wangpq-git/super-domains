import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.schemas.alert_rule import AlertRuleCreate, AlertRuleUpdate
from app.services.notification_service import send_email, send_dingtalk, send_wechat, send_feishu

logger = logging.getLogger(__name__)


async def get_alert_rules(db: AsyncSession) -> list[AlertRule]:
    result = await db.execute(
        select(AlertRule).order_by(AlertRule.created_at.desc())
    )
    return list(result.scalars().all())


async def get_alert_rule(db: AsyncSession, rule_id: int) -> AlertRule | None:
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id)
    )
    return result.scalar_one_or_none()


async def create_alert_rule(db: AsyncSession, data: AlertRuleCreate, user_id: int | None = None) -> AlertRule:
    rule = AlertRule(
        name=data.name,
        rule_type=data.rule_type,
        days_before=data.days_before,
        is_enabled=data.is_enabled,
        channels=data.channels,
        recipients=data.recipients,
        apply_to_all=data.apply_to_all,
        specific_platforms=data.specific_platforms,
        specific_domains=data.specific_domains,
        created_by=user_id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def update_alert_rule(db: AsyncSession, rule_id: int, data: AlertRuleUpdate) -> AlertRule | None:
    rule = await get_alert_rule(db, rule_id)
    if not rule:
        return None

    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_alert_rule(db: AsyncSession, rule_id: int) -> bool:
    rule = await get_alert_rule(db, rule_id)
    if not rule:
        return False
    await db.delete(rule)
    await db.commit()
    return True


async def get_expiring_domains(db: AsyncSession, days: int = 30) -> list[dict]:
    now = datetime.utcnow()
    threshold = now + timedelta(days=days)

    result = await db.execute(
        select(
            Domain.id,
            Domain.domain_name,
            Domain.expiry_date,
            Domain.status,
            PlatformAccount.platform,
            PlatformAccount.account_name,
        )
        .outerjoin(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(
            Domain.status != "removed",
            Domain.expiry_date > now,
            Domain.expiry_date <= threshold,
        )
        .order_by(Domain.expiry_date.asc())
    )

    items = []
    for row in result.all():
        days_left = (row.expiry_date.replace(tzinfo=None) - now).days
        items.append({
            "id": row.id,
            "domain_name": row.domain_name,
            "expiry_date": row.expiry_date,
            "days_left": days_left,
            "status": row.status,
            "platform": row.platform,
            "account": row.account_name,
        })

    return items


async def check_expiring_domains(db: AsyncSession) -> dict:
    rules = await get_alert_rules(db)
    enabled_rules = [r for r in rules if r.is_enabled and r.rule_type == "domain_expiry"]

    if not enabled_rules:
        return {"checked": True, "notifications_sent": 0, "message": "No enabled expiry rules"}

    now = datetime.utcnow()
    total_notifications = 0

    for rule in enabled_rules:
        days = rule.days_before or 30
        expiring = await get_expiring_domains(db, days=days)

        if not expiring:
            continue

        if rule.apply_to_all:
            excluded = rule.excluded_platforms if isinstance(rule.excluded_platforms, list) else []
            if excluded:
                domains_to_alert = [d for d in expiring if d["platform"] not in excluded]
            else:
                domains_to_alert = expiring
        else:
            domains_to_alert = []
            if rule.specific_platforms:
                for d in expiring:
                    if d["platform"] in rule.specific_platforms:
                        domains_to_alert.append(d)
            if rule.specific_domains:
                for d in expiring:
                    if d["id"] in rule.specific_domains:
                        domains_to_alert.append(d)
            domains_to_alert = list({d["id"]: d for d in domains_to_alert}.values())

        if not domains_to_alert:
            continue

        title = f"域名到期提醒 ({rule.name})"
        lines = [f"## {title}\n"]
        for d in domains_to_alert:
            lines.append(
                f"- **{d['domain_name']}** | 平台: {d['platform'] or '-'} | "
                f"到期: {d['expiry_date'].strftime('%Y-%m-%d')} | 剩余 {d['days_left']} 天"
            )
        lines.append(f"\n> 共 {len(domains_to_alert)} 个域名即将到期")
        markdown_body = "\n".join(lines)

        channels = rule.channels if isinstance(rule.channels, list) else []
        recipients = rule.recipients if isinstance(rule.recipients, list) else []

        if "email" in channels and recipients:
            email_recipients = [r for r in recipients if "@" in r]
            if email_recipients:
                html_body = markdown_body.replace("\n", "<br>")
                await send_email(email_recipients, title, html_body)
                total_notifications += 1

        if "dingtalk" in channels and recipients:
            for url in recipients:
                if url.startswith("http"):
                    await send_dingtalk(url, title, markdown_body)
                    total_notifications += 1

        if "wechat" in channels and recipients:
            for url in recipients:
                if url.startswith("http"):
                    await send_wechat(url, markdown_body)
                    total_notifications += 1

        if "feishu" in channels and recipients:
            for url in recipients:
                if url.startswith("http"):
                    await send_feishu(url, title, domains_to_alert, severity=rule.severity or "warning")
                    total_notifications += 1

        if "webhook" in channels and recipients:
            for url in recipients:
                if url.startswith("http"):
                    payload = {
                        "title": title,
                        "rule_id": rule.id,
                        "domains": domains_to_alert,
                        "checked_at": now.isoformat(),
                    }
                    from app.services.notification_service import send_webhook
                    await send_webhook(url, payload)
                    total_notifications += 1

    logger.info("Alert check completed: %d notifications sent", total_notifications)

    return {
        "checked": True,
        "checked_at": now.isoformat(),
        "rules_checked": len(enabled_rules),
        "notifications_sent": total_notifications,
    }
