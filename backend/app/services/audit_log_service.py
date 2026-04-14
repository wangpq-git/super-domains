from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.dns_record import DnsRecord
from app.models.domain import Domain
from app.models.user import User

DOMAIN_ACTION_PREFIXES = ("domain.", "dns.", "change_request.")


async def add_audit_log(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip_address=ip_address,
    )
    db.add(log)
    await db.flush()
    return log


def _build_domain_name_expr():
    dns_domain_name = (
        select(Domain.domain_name)
        .join(DnsRecord, DnsRecord.domain_id == Domain.id)
        .where(DnsRecord.id == AuditLog.target_id)
        .scalar_subquery()
    )
    direct_domain_name = (
        select(Domain.domain_name)
        .where(Domain.id == AuditLog.target_id)
        .scalar_subquery()
    )
    return func.coalesce(
        AuditLog.detail["domain_name"].as_string(),
        AuditLog.detail["domain"]["domain_name"].as_string(),
        direct_domain_name,
        dns_domain_name,
    )


async def list_audit_logs(
    db: AsyncSession,
    *,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    scope: str = "all",
) -> dict[str, Any]:
    domain_name_expr = _build_domain_name_expr().label("domain_name")
    actor_name_expr = func.coalesce(User.display_name, User.username).label("actor_name")

    query: Select = (
        select(
            AuditLog,
            actor_name_expr,
            domain_name_expr,
        )
        .outerjoin(User, User.id == AuditLog.user_id)
    )

    if current_user.role != "admin":
        query = query.where(AuditLog.user_id == current_user.id)

    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if scope == "domain":
        query = query.where(
            or_(
                AuditLog.target_type.in_(("domain", "dns_record", "change_request")),
                *[AuditLog.action.like(f"{prefix}%") for prefix in DOMAIN_ACTION_PREFIXES],
            )
        )
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                AuditLog.action.ilike(pattern),
                actor_name_expr.ilike(pattern),
                domain_name_expr.ilike(pattern),
            )
        )

    total = (
        await db.execute(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
    ).scalar_one()

    rows = (
        await db.execute(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "actor_name": actor_name,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "domain_name": domain_name,
            "detail": log.detail or {},
            "ip_address": log.ip_address,
            "created_at": log.created_at,
        }
        for log, actor_name, domain_name in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
