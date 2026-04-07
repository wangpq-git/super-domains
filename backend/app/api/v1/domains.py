from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db
from app.services import domain_service

router = APIRouter()


@router.get("")
async def list_domains(
    platform: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    expiry_start: Optional[str] = Query(default=None),
    expiry_end: Optional[str] = Query(default=None),
    exclude_expired: bool = Query(default=False),
    dns_manageable_only: bool = Query(default=False),
    sort_by: str = Query("expiry_date", description="排序字段"),
    sort_order: str = Query("asc", description="排序方向 asc/desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await domain_service.list_domains(
        db,
        platform=platform,
        status=status,
        search=search,
        expiry_start=expiry_start,
        expiry_end=expiry_end,
        exclude_expired=exclude_expired,
        dns_manageable_only=dns_manageable_only,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return result


@router.get("/stats")
async def get_domain_stats(db: AsyncSession = Depends(get_db)):
    stats = await domain_service.get_domain_stats(db)
    return stats


@router.get("/{domain_id}")
async def get_domain_detail(domain_id: int, db: AsyncSession = Depends(get_db)):
    detail = await domain_service.get_domain_detail(db, domain_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    return detail
