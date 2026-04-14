from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.audit_log import AuditLogListResponse
from app.services import audit_log_service

router = APIRouter()


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    scope: str = Query(default="all", pattern="^(all|operation|domain)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_scope = "all" if scope == "operation" else scope
    return await audit_log_service.list_audit_logs(
        db,
        current_user=current_user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        action=action,
        target_type=target_type,
        scope=normalized_scope,
    )
