from datetime import datetime, date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.audit_log import AuditLog
from app.schemas.report import AuditLogListResponse


def log_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    target_type: Optional[str],
    target_id: Optional[int],
    detail: dict,
    ip_address: Optional[str],
) -> AuditLog:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip_address=ip_address,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def list_audit_logs(
    db: Session,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    page: int = 1,
    page_size: int = 20,
):
    query = db.query(AuditLog)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if date_start:
        query = query.filter(func.date(AuditLog.created_at) >= date_start)
    if date_end:
        query = query.filter(func.date(AuditLog.created_at) <= date_end)

    total = query.count()
    items = (
        query.order_by(desc(AuditLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return items, total
