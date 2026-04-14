from typing import Literal
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.platform_account import PlatformAccount
from app.models.user import User
from app.schemas.change_request import ChangeRequestResponse
from app.services import audit_log_service, change_request_service

router = APIRouter()


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class DnsRecordBatchItem(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    ttl: int = 3600
    priority: int | None = None
    proxied: bool | None = None


class BatchDnsRequest(BaseModel):
    domain_ids: list[int]
    records: list[DnsRecordBatchItem]
    action: Literal["add", "replace"] = "add"


class BatchSyncRequest(BaseModel):
    account_ids: list[int]


class BatchNameserverRequest(BaseModel):
    domain_ids: list[int]
    nameservers: list[str]


@router.post("/dns", response_model=ChangeRequestResponse, status_code=202)
async def batch_update_dns(
    body: BatchDnsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = body.model_dump()
    try:
        if await change_request_service.should_require_approval(db, current_user):
            result = await change_request_service.create_batch_dns_request(db, current_user, payload)
        else:
            result = await change_request_service.execute_batch_dns_direct(db, current_user, payload)
        await audit_log_service.add_audit_log(
            db,
            user_id=current_user.id,
            action="dns.batch_update",
            target_type="domain",
            target_id=None,
            detail={"domain_ids": body.domain_ids, "record_count": len(body.records), "status": result.status},
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad_request(str(exc))


@router.post("/sync")
async def batch_sync_accounts(
    body: BatchSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = []
    for account_id in body.account_ids:
        from sqlalchemy import select
        result = await db.execute(select(PlatformAccount).where(PlatformAccount.id == account_id))
        account = result.scalar_one_or_none()
        if not account:
            results.append({"account_id": account_id, "status": "error", "message": "账户不存在"})
            continue

        account.sync_status = "syncing"
        account.sync_error = None
        await db.commit()
        results.append({"account_id": account_id, "account_name": account.account_name, "platform": account.platform, "status": "syncing"})

    await audit_log_service.add_audit_log(
        db,
        user_id=current_user.id,
        action="platform.batch_sync",
        target_type="platform_account",
        target_id=None,
        detail={"account_ids": body.account_ids, "total": len(body.account_ids)},
    )
    await db.commit()
    return {"total": len(body.account_ids), "results": results}


@router.post("/nameservers", response_model=ChangeRequestResponse, status_code=202)
async def batch_update_nameservers(
    body: BatchNameserverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = body.model_dump()
    try:
        if await change_request_service.should_require_approval(db, current_user):
            result = await change_request_service.create_batch_nameserver_request(db, current_user, payload)
        else:
            result = await change_request_service.execute_batch_nameserver_direct(db, current_user, payload)
        await audit_log_service.add_audit_log(
            db,
            user_id=current_user.id,
            action="domain.batch_nameserver_update",
            target_type="domain",
            target_id=None,
            detail={"domain_ids": body.domain_ids, "nameservers": body.nameservers, "status": result.status},
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise _bad_request(str(exc))
