import logging
from typing import Literal
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.adapters import get_adapter
from app.adapters.base import DnsRecordInfo
from app.core.encryption import decrypt_credentials
from app.services.dns_service import _get_domain

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.post("/dns")
async def batch_update_dns(
    body: BatchDnsRequest,
    db: AsyncSession = Depends(get_db),
):
    results = []
    for domain_id in body.domain_ids:
        domain = await _get_domain(db, domain_id)
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue

        try:
            account = domain.account
            credentials = decrypt_credentials(account.credentials)
            adapter_cls = get_adapter(account.platform, credentials)

            record_infos = [
                DnsRecordInfo(
                    record_type=r.record_type,
                    name=r.name,
                    content=r.content,
                    ttl=r.ttl,
                    priority=r.priority,
                    proxied=r.proxied,
                )
                for r in body.records
            ]

            async with adapter_cls:
                if body.action == "replace":
                    existing = await adapter_cls.list_dns_records(domain.domain_name)
                    for existing_rec in existing:
                        if existing_rec.external_id:
                            await adapter_cls.delete_dns_record(domain.domain_name, existing_rec.external_id)
                for rec_info in record_infos:
                    await adapter_cls.create_dns_record(domain.domain_name, rec_info)

            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "success"})
        except Exception as e:
            logger.error("Batch DNS update failed for domain %s: %s", domain.domain_name, e)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(e)})

    return {"total": len(body.domain_ids), "results": results}


@router.post("/sync")
async def batch_sync_accounts(
    body: BatchSyncRequest,
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

    return {"total": len(body.account_ids), "results": results}


@router.post("/nameservers")
async def batch_update_nameservers(
    body: BatchNameserverRequest,
    db: AsyncSession = Depends(get_db),
):
    results = []
    for domain_id in body.domain_ids:
        from sqlalchemy import select
        result = await db.execute(select(Domain).where(Domain.id == domain_id))
        domain = result.scalar_one_or_none()
        if not domain:
            results.append({"domain_id": domain_id, "status": "error", "message": "域名不存在"})
            continue

        try:
            account = domain.account
            credentials = decrypt_credentials(account.credentials)
            adapter_cls = get_adapter(account.platform, credentials)

            async with adapter_cls:
                pass

            domain.nameservers = body.nameservers
            await db.commit()
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "success", "nameservers": body.nameservers})
        except Exception as e:
            logger.error("Batch nameserver update failed for domain %s: %s", domain.domain_name, e)
            results.append({"domain_id": domain_id, "domain_name": domain.domain_name, "status": "error", "message": str(e)})

    return {"total": len(body.domain_ids), "results": results}
