import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


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
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

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


FEISHU_SEVERITY_MAP = {
    "urgent": {"icon": "🔴", "label": "紧急", "color": "red"},
    "warning": {"icon": "🟡", "label": "警告", "color": "orange"},
    "info": {"icon": "🟢", "label": "提醒", "color": "green"},
}


async def send_feishu(webhook_url: str, title: str, domains: list[dict], severity: str = "warning") -> bool:
    """发送飞书机器人消息（卡片格式，按告警等级显示颜色）"""
    sev = FEISHU_SEVERITY_MAP.get(severity, FEISHU_SEVERITY_MAP["warning"])

    lines = [f"**{sev['icon']} {sev['label']}** · 共 **{len(domains)}** 个域名"]
    lines.append("")
    for d in domains:
        days = d["days_left"]
        if days <= 3:
            days_text = f"**🔥 {days}天**"
        elif days <= 7:
            days_text = f"**⚠️ {days}天**"
        else:
            days_text = f"{days}天"
        lines.append(
            f"• {d['domain_name']}　`{d['platform'] or '-'}`　"
            f"{d['expiry_date'].strftime('%m-%d')}　{days_text}"
        )

    elements = [
        {"tag": "markdown", "content": "\n".join(lines)},
        {"tag": "hr"},
        {"tag": "note", "elements": [
            {"tag": "plain_text", "content": f"域名管理平台 · {severity.upper()}"}
        ]},
    ]

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": sev["color"]
            },
            "elements": elements
        }
    }
    return await send_webhook(webhook_url, payload)
