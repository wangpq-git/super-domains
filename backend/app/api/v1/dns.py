from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.models.domain import Domain
from app.schemas.dns_record import (
    DnsRecordCreate,
    DnsRecordUpdate,
    DnsRecordResponse,
)
from app.services import dns_service

router = APIRouter()


@router.get("/{domain_id}/records", response_model=list[DnsRecordResponse])
async def list_dns_records(
    domain_id: int,
    sort_by: str = Query("record_type", description="排序字段"),
    sort_order: str = Query("asc", description="排序方向 asc/desc"),
    db: AsyncSession = Depends(get_db),
):
    try:
        records = await dns_service.list_dns_records(db, domain_id, sort_by=sort_by, sort_order=sort_order)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return records


@router.post("/{domain_id}/sync")
async def sync_dns_records(domain_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await dns_service.sync_dns_records(db, domain_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        return {"domain_id": domain_id, "upserted": 0, "removed": 0, "error": str(e)}
    except Exception as e:
        return {"domain_id": domain_id, "upserted": 0, "removed": 0, "error": str(e)}
    return result


@router.post("/{domain_id}/records", response_model=DnsRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_dns_record(
    domain_id: int,
    data: DnsRecordCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await dns_service.create_dns_record(db, domain_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return record


@router.put("/records/{record_id}", response_model=DnsRecordResponse)
async def update_dns_record(
    record_id: int,
    data: DnsRecordUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        record = await dns_service.update_dns_record(db, record_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DNS record not found")
    return record


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dns_record(
    record_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await dns_service.delete_dns_record(db, record_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
