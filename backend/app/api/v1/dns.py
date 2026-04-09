from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.change_request import ChangeRequestResponse
from app.schemas.dns_record import (
    DnsRecordCreate,
    DnsRecordUpdate,
    DnsRecordResponse,
)
from app.services import change_request_service, dns_service

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


@router.post("/{domain_id}/records", response_model=ChangeRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_dns_record(
    domain_id: int,
    data: DnsRecordCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        if await change_request_service.should_require_approval(db, current_user):
            record = await change_request_service.create_dns_create_request(db, current_user, domain_id, data)
        else:
            record = await change_request_service.execute_dns_create_direct(db, current_user, domain_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return record


@router.put("/records/{record_id}", response_model=ChangeRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def update_dns_record(
    record_id: int,
    data: DnsRecordUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        if await change_request_service.should_require_approval(db, current_user):
            record = await change_request_service.create_dns_update_request(db, current_user, record_id, data)
        else:
            record = await change_request_service.execute_dns_update_direct(db, current_user, record_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return record


@router.delete("/records/{record_id}", response_model=ChangeRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def delete_dns_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        if await change_request_service.should_require_approval(db, current_user):
            return await change_request_service.create_dns_delete_request(db, current_user, record_id)
        return await change_request_service.execute_dns_delete_direct(db, current_user, record_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
