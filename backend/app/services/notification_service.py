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
        except Exception as e:
            logger.error("Failed to send email to %s: %s", recipient, e)

    return True


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


async def send_feishu(webhook_url: str, title: str, domains: list[dict]) -> bool:
    """发送飞书机器人消息（卡片+表格格式）"""
    # 按剩余天数分组：紧急(<=3天)、警告(<=7天)、提醒(>7天)
    urgent = [d for d in domains if d["days_left"] <= 3]
    warning = [d for d in domains if 3 < d["days_left"] <= 7]
    normal = [d for d in domains if d["days_left"] > 7]

    elements = []

    def _add_group(label: str, color: str, items: list[dict]):
        if not items:
            return
        lines = [f"**{label}**（{len(items)} 个）"]
        for d in items:
            lines.append(
                f"• {d['domain_name']}　`{d['platform'] or '-'}`　"
                f"{d['expiry_date'].strftime('%m-%d')}　**{d['days_left']}天**"
            )
        elements.append({
            "tag": "column_set",
            "columns": [{
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{"tag": "markdown", "content": "\n".join(lines)}]
            }]
        })
        elements.append({"tag": "hr"})

    _add_group("🔴 紧急（≤3天）", "red", urgent)
    _add_group("🟡 警告（4-7天）", "orange", warning)
    _add_group("🟢 提醒（>7天）", "green", normal)

    # 底部统计
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": f"共 {len(domains)} 个域名即将到期 | 域名管理平台"}]
    })

    # 根据紧急程度选卡片头颜色
    if urgent:
        header_color = "red"
    elif warning:
        header_color = "orange"
    else:
        header_color = "yellow"

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": header_color
            },
            "elements": elements
        }
    }
    return await send_webhook(webhook_url, payload)
