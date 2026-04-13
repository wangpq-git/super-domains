import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.encryption import decrypt_credentials
from app.adapters import get_adapter
from app.adapters.base import DnsRecordInfo
from app.models.change_request import ChangeRequest
from app.models.change_request_event import ChangeRequestEvent
from app.models.dns_record import DnsRecord
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.models.user import User
from app.schemas.dns_record import DnsRecordCreate, DnsRecordUpdate
from app.services import dns_service, system_setting_service
from app.services.dns_validation import validate_dns_record_fields, validate_nameserver_list
from app.services.notification_service import send_feishu_bot_interactive_message, send_webhook

logger = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXECUTING = "executing"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

OP_DNS_CREATE = "dns_create"
OP_DNS_UPDATE = "dns_update"
OP_DNS_DELETE = "dns_delete"
OP_BATCH_DNS_UPDATE = "batch_dns_update"
OP_BATCH_NAMESERVER_UPDATE = "batch_nameserver_update"
OP_CLOUDFLARE_ONBOARD = "cloudflare_onboard"

TERMINAL_STATUSES = {
    STATUS_REJECTED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELLED,
}

CLOUDFLARE_PLATFORM = "cloudflare"
CLOUDFLARE_ONLY_CHANGE_MESSAGE = "目前仅支持修改 Cloudflare 平台上的域名"
NAMESERVER_UPDATE_SUPPORTED_PLATFORMS = {"dynadot"}
NAMESERVER_UPDATE_ONLY_MESSAGE = "目前仅支持修改 Dynadot 域名的 NS"
CLOUDFLARE_ONBOARD_ONLY_MESSAGE = "目前仅支持将 Dynadot 域名接入 Cloudflare"
CLOUDFLARE_ACCOUNT_DOMAIN_LIMIT = 80
CLOUDFLARE_CACHE_RULE_DESCRIPTION = "Cache Everything"
CLOUDFLARE_CACHE_RULE_EXPRESSION = '(not starts_with(http.request.uri.path, "/api/")) or (not starts_with(http.request.uri.path, "/wp-"))'


async def _get_domain(db: AsyncSession, domain_id: int) -> Domain | None:
    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id == domain_id)
    )
    return result.scalar_one_or_none()


async def _get_dns_record(db: AsyncSession, record_id: int) -> DnsRecord | None:
    result = await db.execute(
        select(DnsRecord)
        .options(selectinload(DnsRecord.domain).selectinload(Domain.account))
        .where(DnsRecord.id == record_id)
    )
    return result.scalar_one_or_none()


async def _get_change_request_for_update(db: AsyncSession, change_request_id: int) -> ChangeRequest | None:
    result = await db.execute(
        select(ChangeRequest)
        .where(ChangeRequest.id == change_request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


def _domain_platform(domain: Domain | None) -> str:
    if not domain or not domain.account or not domain.account.platform:
        return ""
    return str(domain.account.platform).lower()


def _ensure_domain_change_supported(domain: Domain | None) -> None:
    if _domain_platform(domain) != CLOUDFLARE_PLATFORM:
        raise ValueError(CLOUDFLARE_ONLY_CHANGE_MESSAGE)


def _ensure_domains_change_supported(domains: list[Domain]) -> None:
    unsupported = [domain.domain_name for domain in domains if _domain_platform(domain) != CLOUDFLARE_PLATFORM]
    if unsupported:
        raise ValueError(f"{CLOUDFLARE_ONLY_CHANGE_MESSAGE}: {', '.join(unsupported[:3])}")


def _ensure_nameserver_change_supported(domain: Domain | None) -> None:
    if _domain_platform(domain) not in NAMESERVER_UPDATE_SUPPORTED_PLATFORMS:
        raise ValueError(NAMESERVER_UPDATE_ONLY_MESSAGE)


def _ensure_nameserver_changes_supported(domains: list[Domain]) -> None:
    unsupported = [
        domain.domain_name
        for domain in domains
        if _domain_platform(domain) not in NAMESERVER_UPDATE_SUPPORTED_PLATFORMS
    ]
    if unsupported:
        raise ValueError(f"{NAMESERVER_UPDATE_ONLY_MESSAGE}: {', '.join(unsupported[:3])}")


def _ensure_cloudflare_onboard_supported(domain: Domain | None) -> None:
    if _domain_platform(domain) not in NAMESERVER_UPDATE_SUPPORTED_PLATFORMS:
        raise ValueError(CLOUDFLARE_ONBOARD_ONLY_MESSAGE)


async def _find_existing_cloudflare_domain(db: AsyncSession, domain_name: str) -> Domain | None:
    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .join(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(
            Domain.domain_name == domain_name,
            Domain.status != "removed",
            PlatformAccount.platform == CLOUDFLARE_PLATFORM,
        )
    )
    return result.scalars().first()


async def _select_cloudflare_target_account(db: AsyncSession) -> tuple[PlatformAccount, int]:
    result = await db.execute(
        select(
            PlatformAccount,
            func.count(Domain.id).label("domain_count"),
        )
        .outerjoin(
            Domain,
            (Domain.account_id == PlatformAccount.id) & (Domain.status != "removed"),
        )
        .where(
            PlatformAccount.platform == CLOUDFLARE_PLATFORM,
            PlatformAccount.is_active == True,
        )
        .group_by(PlatformAccount.id)
        .having(func.count(Domain.id) < CLOUDFLARE_ACCOUNT_DOMAIN_LIMIT)
        .order_by(func.count(Domain.id).asc(), PlatformAccount.id.asc())
    )
    row = result.first()
    if not row:
        raise ValueError(f"没有可用的 Cloudflare 账号（要求域名数 < {CLOUDFLARE_ACCOUNT_DOMAIN_LIMIT}）")
    return row[0], int(row[1] or 0)


async def _add_event(
    db: AsyncSession,
    change_request: ChangeRequest,
    *,
    event_type: str,
    actor_type: str,
    actor_id: int | None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        ChangeRequestEvent(
            change_request_id=change_request.id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            detail=detail or {},
        )
    )
    await db.flush()


def build_feishu_change_request_card(
    change_request: ChangeRequest,
    *,
    include_actions: bool = True,
    result_note: str | None = None,
    base_url: str = "",
) -> dict[str, Any]:
    def _display_value(value: Any, default: str = "-") -> str:
        if value is None:
            return default
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or default
        if isinstance(value, (list, tuple, set)):
            rendered = ", ".join(str(item) for item in value if item is not None)
            return rendered or default
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _field(label: str, value: Any, *, is_short: bool = True) -> dict[str, Any]:
        return {
            "is_short": is_short,
            "text": {
                "tag": "plain_text",
                "content": f"{label}\n{_display_value(value)}",
            },
        }

    def _section(title: str, lines: list[str]) -> dict[str, Any]:
        return {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"{title}\n" + "\n".join(lines),
            },
        }

    operation_labels = {
        OP_DNS_CREATE: "新增 DNS 记录",
        OP_DNS_UPDATE: "修改 DNS 记录",
        OP_DNS_DELETE: "删除 DNS 记录",
        OP_BATCH_DNS_UPDATE: "批量修改 DNS",
        OP_BATCH_NAMESERVER_UPDATE: "批量修改 NS",
        OP_CLOUDFLARE_ONBOARD: "接入 Cloudflare",
    }
    status_labels = {
        STATUS_PENDING: "待审批",
        STATUS_APPROVED: "已批准",
        STATUS_REJECTED: "已拒绝",
        STATUS_EXECUTING: "执行中",
        STATUS_SUCCEEDED: "已执行",
        STATUS_FAILED: "执行失败",
        STATUS_CANCELLED: "已取消",
    }
    risk_labels = {
        "low": "低",
        "medium": "中",
        "high": "高",
    }
    header_templates = {
        STATUS_PENDING: "orange",
        STATUS_APPROVED: "turquoise",
        STATUS_EXECUTING: "blue",
        STATUS_SUCCEEDED: "green",
        STATUS_REJECTED: "red",
        STATUS_FAILED: "red",
        STATUS_CANCELLED: "grey",
    }

    base_url = base_url.rstrip("/")
    payload_data = change_request.payload.get("data", {}) if isinstance(change_request.payload, dict) else {}
    before_snapshot = change_request.before_snapshot or {}
    after_snapshot = change_request.after_snapshot or {}
    merged_snapshot = {**before_snapshot, **after_snapshot}
    created_at = (
        change_request.created_at.replace(tzinfo=UTC).astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
        if change_request.created_at
        else "-"
    )
    domain_name = (
        (change_request.payload.get("domain_name") if isinstance(change_request.payload, dict) else None)
        or payload_data.get("domain_name")
        or merged_snapshot.get("domain_name")
        or (f"ID {change_request.domain_id}" if change_request.domain_id else "-")
    )
    record_type = payload_data.get("record_type") or merged_snapshot.get("record_type") or "-"
    record_name = payload_data.get("name") or merged_snapshot.get("name") or "@"
    record_value = payload_data.get("content") or merged_snapshot.get("content") or "-"
    ttl = payload_data.get("ttl") or merged_snapshot.get("ttl") or "-"
    status_label = status_labels.get(change_request.status, change_request.status)
    operation_label = operation_labels.get(change_request.operation_type, change_request.operation_type)
    risk_label = risk_labels.get(change_request.risk_level, change_request.risk_level or "-")
    header_template = header_templates.get(change_request.status, "blue")
    requester_name = change_request.requester_name or str(change_request.requester_user_id)
    summary_text = f"{_display_value(domain_name)} · {status_label}"
    if result_note:
        summary_text = f"{_display_value(domain_name)} · {status_label}"

    if change_request.operation_type == OP_CLOUDFLARE_ONBOARD:
        execution = change_request.execution_result or {}
        target_account_name = (
            (change_request.payload.get("target_account_name") if isinstance(change_request.payload, dict) else None)
            or execution.get("target_account_name")
            or "-"
        )
        source_platform = (
            (change_request.payload.get("source_platform") if isinstance(change_request.payload, dict) else None)
            or "-"
        )
        nameservers = execution.get("nameservers") or "-"
        cache_rule_expression = (
            (change_request.payload.get("cache_rule", {}) if isinstance(change_request.payload, dict) else {}).get("expression")
            or "-"
        )
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"{operation_label}\n{summary_text}",
                },
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"风险等级：{risk_label}",
                    }
                ],
            },
            {
                "tag": "div",
                "fields": [
                    _field("域名", domain_name),
                    _field("来源平台", source_platform),
                    _field("目标账号", target_account_name),
                    _field("默认代理", "开启"),
                ],
            },
            _section("缓存规则", [cache_rule_expression]),
            _section("目标 NS", [_display_value(nameservers)]),
            {"tag": "hr"},
            _section(
                "审批信息",
                [
                    f"申请人：{_display_value(requester_name)}",
                    f"提交时间：{created_at}",
                    f"变更单号：{_display_value(change_request.request_no)}",
                ],
            ),
        ]
        if result_note:
            elements.append(_section("处理结果", [_display_value(result_note)]))
        else:
            elements.append(_section("当前状态", [status_label]))
        if include_actions:
            elements.append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "批准"},
                            "type": "primary",
                            "value": json.dumps({"action": "approve", "request_id": change_request.id}, ensure_ascii=False),
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "拒绝"},
                            "type": "danger",
                            "value": json.dumps({"action": "reject", "request_id": change_request.id}, ensure_ascii=False),
                        },
                    ],
                }
            )
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"请求 ID：{change_request.id} · 目标类型：{change_request.target_type}",
                    }
                ],
            }
        )
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": header_template,
                "title": {"tag": "plain_text", "content": f"{operation_label} · {status_label}"},
            },
            "elements": elements,
        }

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"{operation_label}\n{summary_text}",
            },
        },
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"风险等级：{risk_label}",
                }
            ],
        },
        {
            "tag": "div",
            "fields": [
                _field("域名", domain_name),
                _field("记录类型", record_type),
                _field("主机记录", record_name),
                _field("TTL", ttl),
            ],
        },
        _section("记录值", [_display_value(record_value)]),
        {"tag": "hr"},
        _section(
            "审批信息",
            [
                f"申请人：{_display_value(requester_name)}",
                f"提交时间：{created_at}",
                f"变更单号：{_display_value(change_request.request_no)}",
            ],
        ),
    ]
    if result_note:
        elements.append(_section("处理结果", [_display_value(result_note)]))
    else:
        elements.append(_section("当前状态", [status_label]))
    if include_actions:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "批准"},
                        "type": "primary",
                        "value": {
                            "action": "approve",
                            "request_id": str(change_request.id),
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "拒绝"},
                        "type": "danger",
                        "value": {
                            "action": "reject",
                            "request_id": str(change_request.id),
                        },
                    },
                ],
            }
        )
    elements.append(
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"请求 ID：{change_request.id} · 目标类型：{change_request.target_type}",
                }
            ],
        }
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "update_multi": True,
        },
        "header": {
            "template": header_template,
            "title": {"tag": "plain_text", "content": f"{operation_label} · {status_label}"},
        },
        "elements": elements,
    }


def build_change_request_result_note(change_request: ChangeRequest) -> str:
    approver_name = change_request.approver_name or str(change_request.approver_user_id or "-")
    if change_request.status == STATUS_REJECTED:
        suffix = f" 原因: {change_request.rejection_reason}" if change_request.rejection_reason else ""
        return f"已由 {approver_name} 拒绝。{suffix}".strip()
    if change_request.status == STATUS_SUCCEEDED:
        return f"已由 {approver_name} 审批通过，执行成功。"
    if change_request.status == STATUS_FAILED:
        suffix = f" 错误: {change_request.error_message}" if change_request.error_message else ""
        return f"已由 {approver_name} 审批通过，但执行失败。{suffix}".strip()
    if change_request.status == STATUS_APPROVED:
        return f"已由 {approver_name} 审批通过。"
    if change_request.status == STATUS_EXECUTING:
        return f"已由 {approver_name} 审批通过，正在执行。"
    if change_request.status == STATUS_CANCELLED:
        return "该变更单已取消。"
    return f"当前状态: {change_request.status}"


async def _notify_change_request(db: AsyncSession, change_request: ChangeRequest) -> None:
    webhook_url = await system_setting_service.get_string(db, "FEISHU_APPROVAL_WEBHOOK_URL")
    base_url = await system_setting_service.get_string(db, "FEISHU_APPROVAL_BASE_URL")
    app_id = await system_setting_service.get_string(db, "FEISHU_BOT_APP_ID")
    app_secret = await system_setting_service.get_string(db, "FEISHU_BOT_APP_SECRET")
    chat_id = await system_setting_service.get_string(db, "FEISHU_APPROVAL_CHAT_ID")
    card = build_feishu_change_request_card(change_request, base_url=base_url)

    if app_id and app_secret and chat_id:
        sent_message_id = await send_feishu_bot_interactive_message(
            app_id=app_id,
            app_secret=app_secret,
            chat_id=chat_id,
            card=card,
        )
        if sent_message_id:
            if isinstance(change_request.payload, dict):
                change_request.payload = {
                    **change_request.payload,
                    "feishu_message_id": sent_message_id,
                }
                await db.commit()
            return

    if not webhook_url:
        return
    payload = {"msg_type": "interactive", "card": card}
    await send_webhook(webhook_url, payload)


async def _notify_change_request_result(db: AsyncSession, change_request: ChangeRequest, result_note: str) -> None:
    webhook_url = await system_setting_service.get_string(db, "FEISHU_APPROVAL_WEBHOOK_URL")
    base_url = await system_setting_service.get_string(db, "FEISHU_APPROVAL_BASE_URL")
    app_id = await system_setting_service.get_string(db, "FEISHU_BOT_APP_ID")
    app_secret = await system_setting_service.get_string(db, "FEISHU_BOT_APP_SECRET")
    chat_id = await system_setting_service.get_string(db, "FEISHU_APPROVAL_CHAT_ID")
    card = build_feishu_change_request_card(
        change_request,
        include_actions=False,
        result_note=result_note,
        base_url=base_url,
    )

    if app_id and app_secret and chat_id:
        sent_message_id = await send_feishu_bot_interactive_message(
            app_id=app_id,
            app_secret=app_secret,
            chat_id=chat_id,
            card=card,
        )
        if sent_message_id:
            return

    if not webhook_url:
        return
    payload = {"msg_type": "interactive", "card": card}
    await send_webhook(webhook_url, payload)


async def should_require_approval(db: AsyncSession, user: User) -> bool:
    approval_enabled = await system_setting_service.get_bool(db, "APPROVAL_ENABLED")
    if not approval_enabled:
        return False
    allow_admin_bypass = await system_setting_service.get_bool(db, "APPROVAL_ALLOW_ADMIN_BYPASS")
    if allow_admin_bypass and user.role == "admin":
        return False
    return True


async def execute_dns_create_direct(db: AsyncSession, user: User, domain_id: int, data: DnsRecordCreate) -> ChangeRequest:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")
    _ensure_domain_change_supported(domain)
    normalized = validate_dns_record_fields(
        record_type=data.record_type,
        name=data.name,
        content=data.content,
        ttl=data.ttl or 3600,
        priority=data.priority,
        proxied=data.proxied,
    )
    payload_data = DnsRecordCreate(**normalized)
    record = await dns_service.create_dns_record(db, domain_id, payload_data)
    now = datetime.now(UTC).replace(tzinfo=None)
    return ChangeRequest(
        id=0,
        request_no=uuid4().hex[:12],
        source="api",
        requester_user_id=user.id,
        requester_name=user.display_name or user.username,
        operation_type=OP_DNS_CREATE,
        target_type="dns_record",
        target_id=record.id,
        domain_id=domain_id,
        payload={"domain_id": domain_id, "domain_name": domain.domain_name, "data": payload_data.model_dump()},
        before_snapshot={"domain_name": domain.domain_name},
        after_snapshot={**payload_data.model_dump(), "domain_name": domain.domain_name},
        risk_level="low",
        status=STATUS_SUCCEEDED,
        approval_channel="direct",
        approver_user_id=user.id,
        approver_name=user.display_name or user.username,
        approved_at=now,
        executed_at=now,
        execution_result={"record_id": record.id, "mode": "direct"},
        expires_at=now,
        created_at=now,
        updated_at=now,
    )


async def execute_dns_update_direct(db: AsyncSession, user: User, record_id: int, data: DnsRecordUpdate) -> ChangeRequest:
    existing = await _get_dns_record(db, record_id)
    if not existing:
        raise ValueError(f"DNS record {record_id} not found")
    domain = await _get_domain(db, existing.domain_id)
    _ensure_domain_change_supported(domain)
    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        raise ValueError("No DNS fields to update")
    validate_dns_record_fields(
        record_type=existing.record_type,
        name=existing.name,
        content=update_fields.get("content", existing.content),
        ttl=update_fields.get("ttl", existing.ttl),
        priority=update_fields.get("priority", existing.priority),
        proxied=update_fields.get("proxied", existing.proxied),
    )
    record = await dns_service.update_dns_record(db, record_id, data)
    now = datetime.now(UTC).replace(tzinfo=None)
    return ChangeRequest(
        id=0,
        request_no=uuid4().hex[:12],
        source="api",
        requester_user_id=user.id,
        requester_name=user.display_name or user.username,
        operation_type=OP_DNS_UPDATE,
        target_type="dns_record",
        target_id=record.id,
        domain_id=record.domain_id,
        payload={
            "record_id": record_id,
            "domain_name": domain.domain_name if domain else None,
            "data": update_fields,
        },
        before_snapshot={},
        after_snapshot={**update_fields, "domain_name": domain.domain_name if domain else None},
        risk_level="low",
        status=STATUS_SUCCEEDED,
        approval_channel="direct",
        approver_user_id=user.id,
        approver_name=user.display_name or user.username,
        approved_at=now,
        executed_at=now,
        execution_result={"record_id": record.id, "mode": "direct"},
        expires_at=now,
        created_at=now,
        updated_at=now,
    )


async def execute_dns_delete_direct(db: AsyncSession, user: User, record_id: int) -> ChangeRequest:
    existing = await _get_dns_record(db, record_id)
    if not existing:
        raise ValueError(f"DNS record {record_id} not found")
    domain = await _get_domain(db, existing.domain_id)
    _ensure_domain_change_supported(domain)
    await dns_service.delete_dns_record(db, record_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    return ChangeRequest(
        id=0,
        request_no=uuid4().hex[:12],
        source="api",
        requester_user_id=user.id,
        requester_name=user.display_name or user.username,
        operation_type=OP_DNS_DELETE,
        target_type="dns_record",
        target_id=record_id,
        domain_id=existing.domain_id,
        payload={"record_id": record_id, "domain_name": domain.domain_name if domain else None},
        before_snapshot={"domain_name": domain.domain_name if domain else None},
        after_snapshot={},
        risk_level="low",
        status=STATUS_SUCCEEDED,
        approval_channel="direct",
        approver_user_id=user.id,
        approver_name=user.display_name or user.username,
        approved_at=now,
        executed_at=now,
        execution_result={"record_id": record_id, "mode": "direct"},
        expires_at=now,
        created_at=now,
        updated_at=now,
    )


def _build_direct_result(
    *,
    user: User,
    operation_type: str,
    target_type: str,
    target_id: int | None,
    domain_id: int | None,
    payload: dict[str, Any],
    execution_result: dict[str, Any],
) -> ChangeRequest:
    now = datetime.now(UTC).replace(tzinfo=None)
    return ChangeRequest(
        id=0,
        request_no=uuid4().hex[:12],
        source="api",
        requester_user_id=user.id,
        requester_name=user.display_name or user.username,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        domain_id=domain_id,
        payload=payload,
        before_snapshot={},
        after_snapshot=payload,
        risk_level="low",
        status=STATUS_SUCCEEDED,
        approval_channel="direct",
        approver_user_id=user.id,
        approver_name=user.display_name or user.username,
        approved_at=now,
        executed_at=now,
        execution_result=execution_result,
        expires_at=now,
        created_at=now,
        updated_at=now,
    )


async def _create_request(
    db: AsyncSession,
    *,
    user: User,
    source: str,
    operation_type: str,
    target_type: str,
    target_id: int | None,
    domain_id: int | None,
    payload: dict[str, Any],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    risk_level: str = "high",
) -> ChangeRequest:
    change_request = ChangeRequest(
        request_no=uuid4().hex[:12],
        source=source,
        requester_user_id=user.id,
        requester_name=user.display_name or user.username,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
        domain_id=domain_id,
        payload=payload,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        risk_level=risk_level,
        status=STATUS_PENDING,
        approval_channel="feishu",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24),
    )
    db.add(change_request)
    await db.flush()
    await _add_event(
        db,
        change_request,
        event_type="submitted",
        actor_type="user",
        actor_id=user.id,
        detail={"source": source},
    )
    await db.commit()
    await db.refresh(change_request)
    try:
        await _notify_change_request(db, change_request)
    except Exception:
        logger.exception("Failed to send change request notification for %s", change_request.request_no)
    await db.refresh(change_request)
    return change_request


async def create_dns_create_request(db: AsyncSession, user: User, domain_id: int, data: DnsRecordCreate) -> ChangeRequest:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")
    _ensure_domain_change_supported(domain)
    normalized = validate_dns_record_fields(
        record_type=data.record_type,
        name=data.name,
        content=data.content,
        ttl=data.ttl or 3600,
        priority=data.priority,
        proxied=data.proxied,
    )
    payload_data = DnsRecordCreate(**normalized)

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_CREATE,
        target_type="dns_record",
        target_id=None,
        domain_id=domain_id,
        payload={"domain_id": domain_id, "domain_name": domain.domain_name, "data": payload_data.model_dump()},
        before_snapshot={"domain_name": domain.domain_name},
        after_snapshot={**payload_data.model_dump(), "domain_name": domain.domain_name},
    )


async def create_dns_update_request(db: AsyncSession, user: User, record_id: int, data: DnsRecordUpdate) -> ChangeRequest:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")
    domain = await _get_domain(db, record.domain_id)
    _ensure_domain_change_supported(domain)
    domain_name = domain.domain_name if domain else None

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        raise ValueError("No DNS fields to update")
    validate_dns_record_fields(
        record_type=record.record_type,
        name=record.name,
        content=update_fields.get("content", record.content),
        ttl=update_fields.get("ttl", record.ttl),
        priority=update_fields.get("priority", record.priority),
        proxied=update_fields.get("proxied", record.proxied),
    )

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_UPDATE,
        target_type="dns_record",
        target_id=record_id,
        domain_id=record.domain_id,
        payload={"record_id": record_id, "domain_name": domain_name, "data": update_fields},
        before_snapshot={
            "id": record.id,
            "domain_name": domain_name,
            "record_type": record.record_type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "priority": record.priority,
            "proxied": record.proxied,
        },
        after_snapshot={**update_fields, "domain_name": domain_name},
    )


async def create_dns_delete_request(db: AsyncSession, user: User, record_id: int) -> ChangeRequest:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")
    domain = await _get_domain(db, record.domain_id)
    _ensure_domain_change_supported(domain)
    domain_name = domain.domain_name if domain else None

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_DELETE,
        target_type="dns_record",
        target_id=record_id,
        domain_id=record.domain_id,
        payload={"record_id": record_id, "domain_name": domain_name},
        before_snapshot={
            "id": record.id,
            "domain_name": domain_name,
            "record_type": record.record_type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "priority": record.priority,
            "proxied": record.proxied,
        },
        after_snapshot={},
    )


async def create_batch_dns_request(db: AsyncSession, user: User, body: dict[str, Any]) -> ChangeRequest:
    domain_ids = body.get("domain_ids") or []
    if not domain_ids:
        raise ValueError("domain_ids is required")
    records = body.get("records") or []
    if not records:
        raise ValueError("records is required")
    normalized_records = [
        validate_dns_record_fields(
            record_type=record.get("record_type", ""),
            name=record.get("name", ""),
            content=record.get("content", ""),
            ttl=record.get("ttl", 3600),
            priority=record.get("priority"),
            proxied=record.get("proxied"),
        )
        for record in records
    ]
    payload = {**body, "records": normalized_records}

    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id.in_(domain_ids))
    )
    domains = result.scalars().all()
    _ensure_domains_change_supported(domains)
    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_BATCH_DNS_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0],
        payload=payload,
        before_snapshot={"domain_ids": domain_ids, "matched_domains": [d.domain_name for d in domains]},
        after_snapshot=payload,
    )


async def create_batch_nameserver_request(db: AsyncSession, user: User, body: dict[str, Any]) -> ChangeRequest:
    domain_ids = body.get("domain_ids") or []
    if not domain_ids:
        raise ValueError("domain_ids is required")
    payload = {**body, "nameservers": validate_nameserver_list(body.get("nameservers") or [])}

    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id.in_(domain_ids))
    )
    domains = result.scalars().all()
    _ensure_nameserver_changes_supported(domains)
    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_BATCH_NAMESERVER_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0],
        payload=payload,
        before_snapshot={
            "domains": [
                {"id": d.id, "domain_name": d.domain_name, "nameservers": d.nameservers}
                for d in domains
            ]
        },
        after_snapshot=payload,
    )


async def execute_batch_dns_direct(db: AsyncSession, user: User, body: dict[str, Any]) -> ChangeRequest:
    records = body.get("records") or []
    if not records:
        raise ValueError("records is required")
    payload = {
        **body,
        "records": [
            validate_dns_record_fields(
                record_type=record.get("record_type", ""),
                name=record.get("name", ""),
                content=record.get("content", ""),
                ttl=record.get("ttl", 3600),
                priority=record.get("priority"),
                proxied=record.get("proxied"),
            )
            for record in records
        ],
    }
    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id.in_(payload.get("domain_ids") or []))
    )
    _ensure_domains_change_supported(result.scalars().all())
    result = await _execute_batch_dns(db, payload)
    domain_ids = payload.get("domain_ids") or []
    return _build_direct_result(
        user=user,
        operation_type=OP_BATCH_DNS_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0] if domain_ids else None,
        payload=payload,
        execution_result=result,
    )


async def execute_batch_nameserver_direct(db: AsyncSession, user: User, body: dict[str, Any]) -> ChangeRequest:
    payload = {**body, "nameservers": validate_nameserver_list(body.get("nameservers") or [])}
    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id.in_(payload.get("domain_ids") or []))
    )
    _ensure_nameserver_changes_supported(result.scalars().all())
    result = await _execute_batch_nameservers(db, payload)
    domain_ids = payload.get("domain_ids") or []
    return _build_direct_result(
        user=user,
        operation_type=OP_BATCH_NAMESERVER_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0] if domain_ids else None,
        payload=payload,
        execution_result=result,
    )


async def create_cloudflare_onboard_request(db: AsyncSession, user: User, domain_id: int) -> ChangeRequest:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")
    _ensure_cloudflare_onboard_supported(domain)

    existing = await _find_existing_cloudflare_domain(db, domain.domain_name)
    if existing:
        raise ValueError(f"域名 {domain.domain_name} 已存在于 Cloudflare 账户 {existing.account.account_name}")

    target_account, domain_count = await _select_cloudflare_target_account(db)
    payload = {
        "source_domain_id": domain.id,
        "source_account_id": domain.account_id,
        "source_platform": _domain_platform(domain),
        "domain_name": domain.domain_name,
        "target_platform": CLOUDFLARE_PLATFORM,
        "target_account_id": target_account.id,
        "target_account_name": target_account.account_name,
        "target_account_domain_count": domain_count,
        "default_proxied": True,
        "cache_rule": {
            "description": CLOUDFLARE_CACHE_RULE_DESCRIPTION,
            "expression": CLOUDFLARE_CACHE_RULE_EXPRESSION,
        },
    }
    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_CLOUDFLARE_ONBOARD,
        target_type="domain",
        target_id=domain.id,
        domain_id=domain.id,
        payload=payload,
        before_snapshot={
            "platform": _domain_platform(domain),
            "account_id": domain.account_id,
            "account_name": domain.account.account_name if domain.account else None,
            "nameservers": domain.nameservers,
        },
        after_snapshot={
            "target_platform": CLOUDFLARE_PLATFORM,
            "target_account_id": target_account.id,
            "target_account_name": target_account.account_name,
            "default_proxied": True,
            "cache_rule_expression": CLOUDFLARE_CACHE_RULE_EXPRESSION,
        },
    )


async def execute_cloudflare_onboard_direct(db: AsyncSession, user: User, domain_id: int) -> ChangeRequest:
    change_request = await create_cloudflare_onboard_request(db, user, domain_id)
    execution_result = await _execute_cloudflare_onboard(db, change_request.payload)
    return _build_direct_result(
        user=user,
        operation_type=OP_CLOUDFLARE_ONBOARD,
        target_type="domain",
        target_id=domain_id,
        domain_id=domain_id,
        payload=change_request.payload,
        execution_result=execution_result,
    )


async def list_change_requests(
    db: AsyncSession,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    operation_type: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    query = select(ChangeRequest)
    if user.role != "admin":
        query = query.where(ChangeRequest.requester_user_id == user.id)
    if status:
        query = query.where(ChangeRequest.status == status)
    if operation_type:
        query = query.where(ChangeRequest.operation_type == operation_type)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            ChangeRequest.request_no.ilike(pattern)
            | ChangeRequest.requester_name.ilike(pattern)
            | ChangeRequest.operation_type.ilike(pattern)
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    result = await db.execute(
        query.order_by(ChangeRequest.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": list(result.scalars().all()),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_change_request(db: AsyncSession, request_id: int, user: User) -> ChangeRequest | None:
    result = await db.execute(select(ChangeRequest).where(ChangeRequest.id == request_id))
    change_request = result.scalar_one_or_none()
    if not change_request:
        return None
    if user.role != "admin" and change_request.requester_user_id != user.id:
        return None
    return change_request


async def get_change_request_by_id(db: AsyncSession, request_id: int) -> ChangeRequest | None:
    result = await db.execute(select(ChangeRequest).where(ChangeRequest.id == request_id))
    return result.scalar_one_or_none()


def is_change_request_processed(change_request: ChangeRequest) -> bool:
    return change_request.status in TERMINAL_STATUSES


async def get_admin_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.role != "admin" or not user.is_active:
        return None
    return user


async def _parse_admin_map(db: AsyncSession) -> dict[str, Any]:
    raw = await system_setting_service.get_json_dict(db, "FEISHU_APPROVAL_ADMIN_MAP")
    return raw if isinstance(raw, dict) else {}


def _normalize_identifier(value: Any, *, lowercase: bool = False) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized.lower() if lowercase else normalized


def _lookup_admin_mapping(admin_map: dict[str, Any], identifier: Any, *, lowercase: bool = False) -> Any:
    normalized = _normalize_identifier(identifier, lowercase=lowercase)
    if normalized is None:
        return None
    if normalized in admin_map:
        return admin_map[normalized]
    raw = str(identifier)
    if raw in admin_map:
        return admin_map[raw]
    return None


async def _get_active_admin_by_field(db: AsyncSession, field: str, value: str) -> User | None:
    column = getattr(User, field)
    if field == "email":
        result = await db.execute(select(User).where(func.lower(column) == value.lower()))
    else:
        result = await db.execute(select(User).where(column == value))
    user = result.scalar_one_or_none()
    if not user or user.role != "admin" or not user.is_active:
        return None
    return user


async def _resolve_mapped_admin_user(db: AsyncSession, mapped: Any) -> User | None:
    if mapped is None:
        return None
    if isinstance(mapped, int) or (isinstance(mapped, str) and mapped.strip().isdigit()):
        return await get_admin_user_by_id(db, int(str(mapped).strip()))
    if not isinstance(mapped, str):
        return None

    normalized = mapped.strip()
    if not normalized:
        return None
    if "@" in normalized:
        user = await _get_active_admin_by_field(db, "email", normalized)
        if user:
            return user

    for field in ("username", "display_name"):
        user = await _get_active_admin_by_field(db, field, normalized)
        if user:
            return user
    return None


async def resolve_admin_user(db: AsyncSession, identifiers: dict[str, Any]) -> User | None:
    email = _normalize_identifier(identifiers.get("email"), lowercase=True)
    username = _normalize_identifier(identifiers.get("username"))
    display_name = username

    admin_map = await _parse_admin_map(db)

    # Prefer email when Feishu provides it so the admin map can stay readable
    # and only require mailbox maintenance in most cases.
    if email:
        user = await _get_active_admin_by_field(db, "email", email)
        if user:
            return user

        mapped = _lookup_admin_mapping(admin_map, email, lowercase=True)
        user = await _resolve_mapped_admin_user(db, mapped)
        if user:
            return user

        if isinstance(mapped, str) and not username:
            username = mapped.strip() or username
            display_name = username

    for key in ("open_id", "union_id", "user_id", "employee_id", "username"):
        mapped = _lookup_admin_mapping(admin_map, identifiers.get(key))
        user = await _resolve_mapped_admin_user(db, mapped)
        if user:
            return user
        if isinstance(mapped, str) and not username:
            username = mapped.strip() or username
            display_name = username

    for field, value in (("username", username), ("display_name", display_name)):
        if not value:
            continue
        user = await _get_active_admin_by_field(db, field, value)
        if user:
            return user

    logger.warning("Unable to resolve Feishu approver from identifiers=%s admin_map_keys=%s", identifiers, sorted(admin_map.keys()))
    return None


async def reject_change_request(
    db: AsyncSession,
    change_request: ChangeRequest,
    approver: User,
    reason: str,
    *,
    send_result_notification: bool = True,
) -> ChangeRequest:
    change_request = await _get_change_request_for_update(db, change_request.id) or change_request
    if change_request.status != STATUS_PENDING:
        raise ValueError("Change request has already been processed")

    change_request.status = STATUS_REJECTED
    change_request.approver_user_id = approver.id
    change_request.approver_name = approver.display_name or approver.username
    change_request.rejected_at = datetime.now(UTC).replace(tzinfo=None)
    change_request.rejection_reason = reason
    await _add_event(
        db,
        change_request,
        event_type="rejected",
        actor_type="user",
        actor_id=approver.id,
        detail={"reason": reason},
    )
    await db.commit()
    await db.refresh(change_request)
    if send_result_notification:
        try:
            await _notify_change_request_result(
                db,
                change_request,
                build_change_request_result_note(change_request),
            )
        except Exception:
            logger.exception("Failed to send rejection notification for %s", change_request.request_no)
    return change_request


async def cancel_change_request(db: AsyncSession, change_request: ChangeRequest, user: User) -> ChangeRequest:
    if change_request.status != STATUS_PENDING:
        raise ValueError("Only pending requests can be cancelled")
    if change_request.requester_user_id != user.id and user.role != "admin":
        raise ValueError("Only requester can cancel this change request")

    change_request.status = STATUS_CANCELLED
    await _add_event(db, change_request, event_type="cancelled", actor_type="user", actor_id=user.id)
    await db.commit()
    await db.refresh(change_request)
    return change_request


async def _execute_batch_dns(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    results = []
    record_infos = [
        DnsRecordInfo(
            record_type=record["record_type"],
            name=record["name"],
            content=record["content"],
            ttl=record.get("ttl", 3600),
            priority=record.get("priority"),
            proxied=record.get("proxied"),
        )
        for record in payload.get("records", [])
    ]
    for domain_id in payload.get("domain_ids", []):
        domain = await dns_service._get_domain_with_account(db, domain_id)
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue
        try:
            _ensure_domain_change_supported(domain)
        except ValueError as exc:
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(exc)})
            continue
        try:
            account = domain.account
            adapter = get_adapter(account.platform, decrypt_credentials(account.credentials))
            async with adapter:
                if payload.get("action") == "replace":
                    existing = await adapter.list_dns_records(domain.domain_name)
                    for existing_rec in existing:
                        if existing_rec.external_id:
                            await adapter.delete_dns_record(domain.domain_name, existing_rec.external_id)
                for record_info in record_infos:
                    await adapter.create_dns_record(domain.domain_name, record_info)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "success"})
        except Exception as exc:
            logger.error("Batch DNS update failed for domain %s: %s", domain.domain_name, exc)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(exc)})
    return {"total": len(payload.get("domain_ids", [])), "results": results}


async def _execute_cloudflare_onboard(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    source_domain = await _get_domain(db, payload["source_domain_id"])
    if not source_domain:
        raise ValueError(f"Domain {payload['source_domain_id']} not found")
    _ensure_cloudflare_onboard_supported(source_domain)

    result = await db.execute(
        select(PlatformAccount).where(PlatformAccount.id == payload["target_account_id"])
    )
    target_account = result.scalar_one_or_none()
    if not target_account or target_account.platform != CLOUDFLARE_PLATFORM or not target_account.is_active:
        raise ValueError("目标 Cloudflare 账号不存在或不可用")

    existing = await _find_existing_cloudflare_domain(db, source_domain.domain_name)
    if existing and existing.account_id != target_account.id:
        raise ValueError(f"域名 {source_domain.domain_name} 已存在于 Cloudflare 账户 {existing.account.account_name}")

    adapter = get_adapter(target_account.platform, decrypt_credentials(target_account.credentials))
    async with adapter:
        zone_result = await adapter.create_zone(source_domain.domain_name)
        cache_rule_result = await adapter.ensure_cache_rule(
            source_domain.domain_name,
            expression=payload["cache_rule"]["expression"],
            description=payload["cache_rule"]["description"],
        )

    nameservers = [str(ns).strip().lower() for ns in (zone_result.get("nameservers") or []) if str(ns).strip()]
    if len(nameservers) < 2:
        raise RuntimeError("Cloudflare zone did not return valid nameservers")

    source_adapter = get_adapter(source_domain.account.platform, decrypt_credentials(source_domain.account.credentials))
    async with source_adapter:
        await source_adapter.update_nameservers(source_domain.domain_name, nameservers)

    cloudflare_domain = existing
    if not cloudflare_domain:
        cloudflare_domain = Domain(
            account_id=target_account.id,
            domain_name=source_domain.domain_name,
            tld=source_domain.tld,
            status=str(zone_result.get("status") or "pending"),
            registration_date=source_domain.registration_date,
            expiry_date=source_domain.expiry_date,
            auto_renew=False,
            locked=False,
            whois_privacy=False,
            nameservers=nameservers,
            external_id=zone_result.get("zone_id"),
            raw_data=zone_result.get("zone") or {},
            last_synced_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(cloudflare_domain)
    else:
        cloudflare_domain.status = str(zone_result.get("status") or cloudflare_domain.status or "pending")
        cloudflare_domain.nameservers = nameservers
        cloudflare_domain.external_id = zone_result.get("zone_id") or cloudflare_domain.external_id
        cloudflare_domain.raw_data = zone_result.get("zone") or cloudflare_domain.raw_data
        cloudflare_domain.last_synced_at = datetime.now(UTC).replace(tzinfo=None)

    source_domain.nameservers = nameservers
    source_domain.raw_data = {
        **(source_domain.raw_data or {}),
        "cloudflare_target_account_id": target_account.id,
        "cloudflare_target_account_name": target_account.account_name,
    }

    await db.commit()
    if cloudflare_domain.id:
        await db.refresh(cloudflare_domain)

    return {
        "source_domain_id": source_domain.id,
        "source_platform": _domain_platform(source_domain),
        "cloudflare_domain_id": cloudflare_domain.id,
        "target_account_id": target_account.id,
        "target_account_name": target_account.account_name,
        "zone_id": zone_result.get("zone_id"),
        "nameservers": nameservers,
        "default_proxied": True,
        "cache_rule": {
            "description": payload["cache_rule"]["description"],
            "expression": payload["cache_rule"]["expression"],
            "rule_id": cache_rule_result.get("rule_id"),
            "ruleset_id": cache_rule_result.get("ruleset_id"),
        },
    }


async def _execute_batch_nameservers(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    nameservers = validate_nameserver_list(payload.get("nameservers", []))
    results = []
    requested_nameservers = [str(ns).strip().lower() for ns in nameservers if str(ns).strip()]

    for domain_id in payload.get("domain_ids", []):
        domain = await _get_domain(db, domain_id)
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue
        try:
            _ensure_nameserver_change_supported(domain)
        except ValueError as exc:
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(exc)})
            continue
        try:
            account = domain.account
            if not account:
                raise RuntimeError("域名缺少平台账户信息")
            adapter = get_adapter(account.platform, decrypt_credentials(account.credentials))
            async with adapter:
                await adapter.update_nameservers(domain.domain_name, requested_nameservers)
            domain.nameservers = requested_nameservers
            results.append({
                "domain_id": domain_id,
                "domain_name": domain.domain_name,
                "status": "success",
                "nameservers": requested_nameservers,
            })
        except Exception as exc:
            logger.error("Batch nameserver update failed for domain %s: %s", domain.domain_name, exc)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(exc)})
    await db.commit()
    return {"total": len(payload.get("domain_ids", [])), "results": results}


async def _execute_change_request(db: AsyncSession, change_request: ChangeRequest) -> dict[str, Any]:
    if change_request.operation_type == OP_DNS_CREATE:
        payload = change_request.payload
        domain = await _get_domain(db, payload["domain_id"])
        _ensure_domain_change_supported(domain)
        record = await dns_service.create_dns_record(db, payload["domain_id"], DnsRecordCreate(**payload["data"]))
        return {"record_id": record.id}
    if change_request.operation_type == OP_DNS_UPDATE:
        payload = change_request.payload
        record_model = await _get_dns_record(db, payload["record_id"])
        _ensure_domain_change_supported(record_model.domain if record_model else None)
        record = await dns_service.update_dns_record(db, payload["record_id"], DnsRecordUpdate(**payload["data"]))
        return {"record_id": record.id}
    if change_request.operation_type == OP_DNS_DELETE:
        payload = change_request.payload
        record_model = await _get_dns_record(db, payload["record_id"])
        _ensure_domain_change_supported(record_model.domain if record_model else None)
        await dns_service.delete_dns_record(db, payload["record_id"])
        return {"record_id": payload["record_id"]}
    if change_request.operation_type == OP_BATCH_DNS_UPDATE:
        return await _execute_batch_dns(db, change_request.payload)
    if change_request.operation_type == OP_CLOUDFLARE_ONBOARD:
        return await _execute_cloudflare_onboard(db, change_request.payload)
    if change_request.operation_type == OP_BATCH_NAMESERVER_UPDATE:
        return await _execute_batch_nameservers(db, change_request.payload)
    raise ValueError(f"Unsupported operation type: {change_request.operation_type}")


async def approve_change_request(
    db: AsyncSession,
    change_request: ChangeRequest,
    approver: User,
    *,
    send_result_notification: bool = True,
) -> ChangeRequest:
    request_id = change_request.id
    change_request = await _get_change_request_for_update(db, request_id) or change_request
    if change_request.status != STATUS_PENDING:
        raise ValueError("Change request has already been processed")

    change_request.status = STATUS_APPROVED
    change_request.approver_user_id = approver.id
    change_request.approver_name = approver.display_name or approver.username
    change_request.approved_at = datetime.now(UTC).replace(tzinfo=None)
    await _add_event(db, change_request, event_type="approved", actor_type="user", actor_id=approver.id)
    await db.commit()

    try:
        change_request.status = STATUS_EXECUTING
        change_request.error_message = None
        await _add_event(db, change_request, event_type="executing", actor_type="system", actor_id=None)
        await db.commit()

        result = await _execute_change_request(db, change_request)
        change_request.status = STATUS_SUCCEEDED
        change_request.executed_at = datetime.now(UTC).replace(tzinfo=None)
        change_request.execution_result = result
        change_request.error_message = None
        await _add_event(db, change_request, event_type="succeeded", actor_type="system", actor_id=None, detail=result)
        await db.commit()
        if send_result_notification:
            try:
                await _notify_change_request_result(
                    db,
                    change_request,
                    build_change_request_result_note(change_request),
                )
            except Exception:
                logger.exception("Failed to send success notification for %s", change_request.request_no)
    except Exception as exc:
        logger.exception("Failed to execute change request %s", request_id)
        await db.rollback()
        change_request = await db.get(ChangeRequest, request_id)
        change_request.status = STATUS_FAILED
        change_request.error_message = str(exc)
        change_request.executed_at = datetime.now(UTC).replace(tzinfo=None)
        change_request.execution_result = {"error": str(exc)}
        await _add_event(
            db,
            change_request,
            event_type="failed",
            actor_type="system",
            actor_id=None,
            detail={"error": str(exc)},
        )
        await db.commit()
        if send_result_notification:
            try:
                await _notify_change_request_result(
                    db,
                    change_request,
                    build_change_request_result_note(change_request),
                )
            except Exception:
                logger.exception("Failed to send failure notification for %s", change_request.request_no)

    await db.refresh(change_request)
    return change_request
