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

FEISHU_PAGE_SIZE = 10


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 1:
        return value[:limit]
    return value[: limit - 1] + "…"


def _build_feishu_columns(
    provider: str,
    domain_name: str,
    expiry_date: str,
    status_text: str,
    bold: bool = False,
) -> dict:
    text_tag = "lark_md" if bold else "plain_text"
    if bold:
        provider = f"**{provider}**"
        domain_name = f"**{domain_name}**"
        expiry_date = f"**{expiry_date}**"
        status_text = f"**{status_text}**"

    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 25,
                "elements": [{"tag": text_tag, "content": provider}],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 35,
                "elements": [{"tag": text_tag, "content": domain_name}],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 22,
                "elements": [{"tag": text_tag, "content": expiry_date}],
            },
            {
                "tag": "column",
                "width": "weighted",
                "weight": 18,
                "elements": [{"tag": text_tag, "content": status_text}],
            },
        ],
    }


def _build_feishu_page_card(
    title: str,
    domains: list[dict],
    severity: str,
    page: int,
    total_pages: int,
    total_domains: int,
) -> dict:
    sev = FEISHU_SEVERITY_MAP.get(severity, FEISHU_SEVERITY_MAP["warning"])

    elements = [
        {
            "tag": "markdown",
            "content": f"**{sev['icon']} {sev['label']}** · 共 **{total_domains}** 个域名",
        },
        {"tag": "hr"},
        _build_feishu_columns("服务商", "域名", "到期时间", "状态", bold=True),
    ]

    for domain in domains:
        provider = _trim_text(str(domain["platform"] or "-"), 18)
        domain_name = _trim_text(str(domain["domain_name"]), 32)
        expiry_date = domain["expiry_date"].strftime("%Y-%m-%d")
        status_text = f"剩余{domain['days_left']}天"
        elements.append({"tag": "hr"})
        elements.append(_build_feishu_columns(provider, domain_name, expiry_date, status_text))

    elements.extend([
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [
                {"tag": "plain_text", "content": f"第 {page} / {total_pages} 页 · 每页 10 条"},
                {"tag": "plain_text", "content": "域名管理平台"},
            ],
        },
    ])

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title if total_pages == 1 else f"{title}（第 {page}/{total_pages} 页）",
                },
                "template": sev["color"],
            },
            "elements": elements,
        },
    }


async def send_feishu(webhook_url: str, title: str, domains: list[dict], severity: str = "warning") -> bool:
    """发送飞书机器人消息（卡片分页样式）"""
    if not domains:
        return True

    total_pages = (len(domains) + FEISHU_PAGE_SIZE - 1) // FEISHU_PAGE_SIZE
    sent_count = 0

    for index in range(total_pages):
        start = index * FEISHU_PAGE_SIZE
        end = start + FEISHU_PAGE_SIZE
        page_domains = domains[start:end]
        payload = _build_feishu_page_card(
            title=title,
            domains=page_domains,
            severity=severity,
            page=index + 1,
            total_pages=total_pages,
            total_domains=len(domains),
        )
        if await send_webhook(webhook_url, payload):
            sent_count += 1

    return sent_count == total_pages
