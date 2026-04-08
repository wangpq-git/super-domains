import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.encryption import decrypt_credentials
from app.adapters import get_adapter
from app.adapters.base import DnsRecordInfo
from app.models.change_request import ChangeRequest
from app.models.change_request_event import ChangeRequestEvent
from app.models.dns_record import DnsRecord
from app.models.domain import Domain
from app.models.user import User
from app.schemas.dns_record import DnsRecordCreate, DnsRecordUpdate
from app.services import dns_service
from app.services.notification_service import send_webhook

logger = logging.getLogger(__name__)

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

TERMINAL_STATUSES = {
    STATUS_REJECTED,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELLED,
}


async def _get_domain(db: AsyncSession, domain_id: int) -> Domain | None:
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    return result.scalar_one_or_none()


async def _get_dns_record(db: AsyncSession, record_id: int) -> DnsRecord | None:
    result = await db.execute(
        select(DnsRecord)
        .options(selectinload(DnsRecord.domain).selectinload(Domain.account))
        .where(DnsRecord.id == record_id)
    )
    return result.scalar_one_or_none()


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
) -> dict[str, Any]:
    base_url = getattr(settings, "FEISHU_APPROVAL_BASE_URL", "").rstrip("/")
    request_detail = {
        "request_no": change_request.request_no,
        "operation_type": change_request.operation_type,
        "status": change_request.status,
        "requester": change_request.requester_name or str(change_request.requester_user_id),
        "domain_id": change_request.domain_id,
        "target_type": change_request.target_type,
        "target_id": change_request.target_id,
        "risk": change_request.risk_level,
    }
    if base_url:
        request_detail["approve_url"] = f"{base_url}/api/v1/change-requests/{change_request.id}/approve"
        request_detail["reject_url"] = f"{base_url}/api/v1/change-requests/{change_request.id}/reject"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**操作**: {change_request.operation_type}\n"
                    f"**申请人**: {change_request.requester_name or change_request.requester_user_id}\n"
                    f"**风险**: {change_request.risk_level}\n"
                    f"**状态**: {change_request.status}\n"
                    f"**详情**: `{json.dumps(request_detail, ensure_ascii=False)}`"
                ),
            },
        }
    ]
    if result_note:
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": result_note,
                    }
                ],
            }
        )
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
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": f"变更审批 #{change_request.request_no}"}},
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


async def _notify_change_request(change_request: ChangeRequest) -> None:
    webhook_url = getattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", None)
    if not webhook_url:
        return

    payload = {
        "msg_type": "interactive",
        "card": build_feishu_change_request_card(change_request),
    }
    await send_webhook(webhook_url, payload)


async def _notify_change_request_result(change_request: ChangeRequest, result_note: str) -> None:
    webhook_url = getattr(settings, "FEISHU_APPROVAL_WEBHOOK_URL", None)
    if not webhook_url:
        return

    payload = {
        "msg_type": "interactive",
        "card": build_feishu_change_request_card(
            change_request,
            include_actions=False,
            result_note=result_note,
        ),
    }
    await send_webhook(webhook_url, payload)


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
        await _notify_change_request(change_request)
    except Exception:
        logger.exception("Failed to send change request notification for %s", change_request.request_no)
    return change_request


async def create_dns_create_request(db: AsyncSession, user: User, domain_id: int, data: DnsRecordCreate) -> ChangeRequest:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_CREATE,
        target_type="dns_record",
        target_id=None,
        domain_id=domain_id,
        payload={"domain_id": domain_id, "data": data.model_dump()},
        before_snapshot={},
        after_snapshot=data.model_dump(),
    )


async def create_dns_update_request(db: AsyncSession, user: User, record_id: int, data: DnsRecordUpdate) -> ChangeRequest:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        raise ValueError("No DNS fields to update")

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_UPDATE,
        target_type="dns_record",
        target_id=record_id,
        domain_id=record.domain_id,
        payload={"record_id": record_id, "data": update_fields},
        before_snapshot={
            "id": record.id,
            "record_type": record.record_type,
            "name": record.name,
            "content": record.content,
            "ttl": record.ttl,
            "priority": record.priority,
            "proxied": record.proxied,
        },
        after_snapshot=update_fields,
    )


async def create_dns_delete_request(db: AsyncSession, user: User, record_id: int) -> ChangeRequest:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_DNS_DELETE,
        target_type="dns_record",
        target_id=record_id,
        domain_id=record.domain_id,
        payload={"record_id": record_id},
        before_snapshot={
            "id": record.id,
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

    result = await db.execute(select(Domain).where(Domain.id.in_(domain_ids)))
    domains = result.scalars().all()
    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_BATCH_DNS_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0],
        payload=body,
        before_snapshot={"domain_ids": domain_ids, "matched_domains": [d.domain_name for d in domains]},
        after_snapshot=body,
    )


async def create_batch_nameserver_request(db: AsyncSession, user: User, body: dict[str, Any]) -> ChangeRequest:
    domain_ids = body.get("domain_ids") or []
    if not domain_ids:
        raise ValueError("domain_ids is required")

    result = await db.execute(select(Domain).where(Domain.id.in_(domain_ids)))
    domains = result.scalars().all()
    return await _create_request(
        db,
        user=user,
        source="api",
        operation_type=OP_BATCH_NAMESERVER_UPDATE,
        target_type="domain",
        target_id=None,
        domain_id=domain_ids[0],
        payload=body,
        before_snapshot={
            "domains": [
                {"id": d.id, "domain_name": d.domain_name, "nameservers": d.nameservers}
                for d in domains
            ]
        },
        after_snapshot=body,
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


def _parse_admin_map() -> dict[str, Any]:
    raw = settings.FEISHU_APPROVAL_ADMIN_MAP
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid FEISHU_APPROVAL_ADMIN_MAP JSON")
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def resolve_admin_user(db: AsyncSession, identifiers: dict[str, Any]) -> User | None:
    local_user_id = identifiers.get("local_user_id")
    if local_user_id is not None:
        try:
            return await get_admin_user_by_id(db, int(local_user_id))
        except (TypeError, ValueError):
            pass

    query_values = {
        "username": identifiers.get("username"),
        "email": identifiers.get("email"),
    }

    admin_map = _parse_admin_map()
    for key in ("open_id", "union_id", "user_id", "employee_id", "username", "email"):
        value = identifiers.get(key)
        if not value:
            continue
        mapped = admin_map.get(str(value))
        if mapped is not None:
            if isinstance(mapped, int) or (isinstance(mapped, str) and str(mapped).isdigit()):
                return await get_admin_user_by_id(db, int(mapped))
            if isinstance(mapped, str):
                query_values.setdefault("username", mapped)

    for field in ("username", "email"):
        value = query_values.get(field)
        if not value:
            continue
        column = getattr(User, field)
        result = await db.execute(select(User).where(column == value))
        user = result.scalar_one_or_none()
        if user and user.role == "admin" and user.is_active:
            return user

    return None


async def reject_change_request(db: AsyncSession, change_request: ChangeRequest, approver: User, reason: str) -> ChangeRequest:
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
    try:
        await _notify_change_request_result(
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
    for domain_id in payload.get("domain_ids", []):
        domain = await dns_service._get_domain_with_account(db, domain_id)
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue
        try:
            account = domain.account
            adapter = get_adapter(account.platform, decrypt_credentials(account.credentials))
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


async def _execute_batch_nameservers(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    results = []
    for domain_id in payload.get("domain_ids", []):
        domain = await _get_domain(db, domain_id)
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue
        try:
            domain.nameservers = payload.get("nameservers", [])
            results.append({
                "domain_id": domain_id,
                "domain_name": domain.domain_name,
                "status": "success",
                "nameservers": payload.get("nameservers", []),
            })
        except Exception as exc:
            logger.error("Batch nameserver update failed for domain %s: %s", domain.domain_name, exc)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(exc)})
    await db.commit()
    return {"total": len(payload.get("domain_ids", [])), "results": results}


async def _execute_change_request(db: AsyncSession, change_request: ChangeRequest) -> dict[str, Any]:
    if change_request.operation_type == OP_DNS_CREATE:
        payload = change_request.payload
        record = await dns_service.create_dns_record(db, payload["domain_id"], DnsRecordCreate(**payload["data"]))
        return {"record_id": record.id}
    if change_request.operation_type == OP_DNS_UPDATE:
        payload = change_request.payload
        record = await dns_service.update_dns_record(db, payload["record_id"], DnsRecordUpdate(**payload["data"]))
        return {"record_id": record.id}
    if change_request.operation_type == OP_DNS_DELETE:
        payload = change_request.payload
        await dns_service.delete_dns_record(db, payload["record_id"])
        return {"record_id": payload["record_id"]}
    if change_request.operation_type == OP_BATCH_DNS_UPDATE:
        return await _execute_batch_dns(db, change_request.payload)
    if change_request.operation_type == OP_BATCH_NAMESERVER_UPDATE:
        return await _execute_batch_nameservers(db, change_request.payload)
    raise ValueError(f"Unsupported operation type: {change_request.operation_type}")


async def approve_change_request(db: AsyncSession, change_request: ChangeRequest, approver: User) -> ChangeRequest:
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
        await _add_event(db, change_request, event_type="executing", actor_type="system", actor_id=None)
        await db.commit()

        result = await _execute_change_request(db, change_request)
        change_request.status = STATUS_SUCCEEDED
        change_request.executed_at = datetime.now(UTC).replace(tzinfo=None)
        change_request.execution_result = result
        await _add_event(db, change_request, event_type="succeeded", actor_type="system", actor_id=None, detail=result)
        await db.commit()
        try:
            await _notify_change_request_result(
                change_request,
                build_change_request_result_note(change_request),
            )
        except Exception:
            logger.exception("Failed to send success notification for %s", change_request.request_no)
    except Exception as exc:
        logger.exception("Failed to execute change request %s", change_request.id)
        await db.rollback()
        change_request = await db.get(ChangeRequest, change_request.id)
        change_request.status = STATUS_FAILED
        change_request.error_message = str(exc)
        change_request.executed_at = datetime.now(UTC).replace(tzinfo=None)
        await _add_event(
            db,
            change_request,
            event_type="failed",
            actor_type="system",
            actor_id=None,
            detail={"error": str(exc)},
        )
        await db.commit()
        try:
            await _notify_change_request_result(
                change_request,
                build_change_request_result_note(change_request),
            )
        except Exception:
            logger.exception("Failed to send failure notification for %s", change_request.request_no)

    await db.refresh(change_request)
    return change_request
