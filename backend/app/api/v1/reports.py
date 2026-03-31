from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import report_service, audit_service
from app.schemas.report import (
    OverviewStats,
    ExpiryReport,
    PlatformReport,
    AuditLogResponse,
    AuditLogListResponse,
)
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return report_service.get_overview(db)


@router.get("/expiry", response_model=ExpiryReport)
async def get_expiry_report(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return report_service.get_expiry_report(db, days)


@router.get("/platforms", response_model=PlatformReport)
async def get_platform_report(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items = report_service.get_platform_report(db)
    return {"items": items}


@router.get("/audit", response_model=AuditLogListResponse)
async def get_audit_logs(
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    date_start: Optional[date] = None,
    date_end: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    items, total = audit_service.list_audit_logs(
        db,
        action=action,
        target_type=target_type,
        date_start=date_start,
        date_end=date_end,
        page=page,
        page_size=page_size,
    )

    from app.models.user import User
    user_map = {u.id: u.username for u in db.query(User).all()}

    audit_items = []
    for log in items:
        audit_items.append(
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                username=user_map.get(log.user_id) if log.user_id else None,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                detail=log.detail or {},
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
        )

    return {
        "items": audit_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/audit", response_model=AuditLogResponse)
async def create_audit_log(
    request: Request,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    detail: dict = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from fastapi.requests import Request
    ip_address = request.client.host if request.client else None
    log = audit_service.log_action(
        db,
        user_id=current_user.id if current_user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
        ip_address=ip_address,
    )
    return AuditLogResponse(
        id=log.id,
        user_id=log.user_id,
        username=current_user.username if current_user else None,
        action=log.action,
        target_type=log.target_type,
        target_id=log.target_id,
        detail=log.detail or {},
        ip_address=log.ip_address,
        created_at=log.created_at,
    )
