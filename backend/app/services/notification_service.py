import logging
from datetime import datetime
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FEISHU_SEVERITY_MAP = {
    "urgent": {"icon": "🔴", "label": "紧急", "color": "red"},
    "warning": {"icon": "🟡", "label": "警告", "color": "orange"},
    "info": {"icon": "🟢", "label": "提醒", "color": "green"},
}


async def send_email(recipients: list[str], subject: str, body: str) -> bool:
    smtp_host = getattr(settings, "SMTP_HOST", None)
    smtp_port = getattr(settings, "SMTP_PORT", 587)
    smtp_user = getattr(settings, "SMTP_USER", None)
    smtp_password = getattr(settings, "SMTP_PASSWORD", None)
    smtp_from = getattr(settings, "SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        logger.warning("Email not configured: SMTP_HOST/SMTP_USER not set")
        return False

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    sent = 0

    for recipient in recipients:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from or smtp_user
            msg["To"] = recipient
            msg.attach(MIMEText(body, "html", "utf-8"))

            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_password,
                use_tls=getattr(settings, "SMTP_USE_TLS", True),
                start_tls=getattr(settings, "SMTP_START_TLS", True),
            )
            logger.info("Email sent to %s: %s", recipient, subject)
            sent += 1
        except Exception as e:
            logger.error("Failed to send email to %s: %s", recipient, e)

    return sent > 0


async def send_webhook(url: str, payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                data = resp.json()
                if isinstance(data, dict) and data.get("code") not in (None, 0):
                    logger.error(
                        "Webhook business error from %s: code=%s msg=%s payload=%s",
                        url,
                        data.get("code"),
                        data.get("msg"),
                        payload,
                    )
                    return False

            logger.info("Webhook sent to %s: status=%d", url, resp.status_code)
            return True
    except Exception as e:
        logger.error("Failed to send webhook to %s: %s", url, e)
        return False


async def send_dingtalk(webhook_url: str, title: str, content: str) -> bool:
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": content,
        },
    }
    return await send_webhook(webhook_url, payload)


async def send_wechat(webhook_url: str, content: str) -> bool:
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
    }
    return await send_webhook(webhook_url, payload)


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1] + "…"


def _build_feishu_template_rows(domains: list[dict]) -> list[dict]:
    rows = []
    for index, domain in enumerate(domains, start=1):
        provider = _trim_text(str(domain.get("platform") or "-"), 18)
        domain_name = _trim_text(str(domain.get("domain_name") or "-"), 64)
        expiry_date = domain["expiry_date"].strftime("%Y-%m-%d")
        days_left = int(domain.get("days_left") or 0)
        status_text = f"剩余{days_left}天"

        rows.append(
            {
                "index": index,
                "provider": provider,
                "platform": provider,
                "domain": domain_name,
                "domain_name": domain_name,
                "expiry_date": expiry_date,
                "expiryDate": expiry_date,
                "status": status_text,
                "days_left": days_left,
                "daysLeft": days_left,
                "remaining_days": days_left,
                "remainingDays": days_left,
            }
        )

    return rows


def _build_feishu_template_card(
    title: str,
    domains: list[dict],
    severity: str,
) -> dict:
    sev = FEISHU_SEVERITY_MAP.get(severity, FEISHU_SEVERITY_MAP["warning"])
    variable_name = settings.FEISHU_CARD_TABLE_VARIABLE
    rows = _build_feishu_template_rows(domains)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template_variable = {
        variable_name: rows,
        "title": title,
        "card_title": title,
        "severity": sev["label"],
        "severity_label": sev["label"],
        "severity_icon": sev["icon"],
        "total": len(domains),
        "total_count": len(domains),
        "updated_at": now_str,
    }

    return {
        "msg_type": "interactive",
        "card": {
            "type": "template",
            "data": {
                "template_id": settings.FEISHU_CARD_TEMPLATE_ID,
                "template_version_name": settings.FEISHU_CARD_TEMPLATE_VERSION,
                "template_variable": template_variable,
            },
        },
    }


async def send_feishu(webhook_url: str, title: str, domains: list[dict], severity: str = "warning") -> bool:
    """Send a Feishu template card message."""
    if not domains:
        return True

    payload = _build_feishu_template_card(title=title, domains=domains, severity=severity)
    return await send_webhook(webhook_url, payload)
