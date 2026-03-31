from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.transfer import DomainTransfer
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.adapters import get_adapter


async def initiate_transfer(
    db: AsyncSession,
    domain_id: int,
    to_platform: str,
    to_account: str,
    user_id: int,
) -> DomainTransfer:
    result = await db.execute(
        select(Domain, PlatformAccount)
        .options(selectinload(Domain.account))
        .where(Domain.id == domain_id)
        .outerjoin(PlatformAccount, PlatformAccount.id == Domain.account_id)
    )
    row = result.one_or_none()
    if not row:
        raise ValueError(f"Domain {domain_id} not found")

    domain, account = row

    auth_code = None
    if account:
        try:
            credentials = {}
            adapter = get_adapter(account.platform, credentials)
            if hasattr(adapter, "get_transfer_auth_code"):
                try:
                    async with adapter:
                        auth_code = await adapter.get_transfer_auth_code(domain.domain_name)
                except Exception:
                    pass
        except Exception:
            pass

    transfer = DomainTransfer(
        domain_id=domain_id,
        from_account_id=domain.account_id,
        to_platform=to_platform,
        to_account=to_account,
        status="pending",
        auth_code=auth_code,
        initiated_at=datetime.utcnow(),
        created_by=user_id,
    )

    db.add(transfer)
    await db.flush()
    await db.refresh(transfer)

    domain.status = "transferring"
    await db.commit()
    await db.refresh(transfer)

    return transfer


async def list_transfers(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    domain_id: Optional[int] = None,
    from_platform: Optional[str] = None,
    to_platform: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = (
        select(
            DomainTransfer.id,
            DomainTransfer.domain_id,
            DomainTransfer.from_account_id,
            DomainTransfer.to_platform,
            DomainTransfer.to_account,
            DomainTransfer.status,
            DomainTransfer.auth_code,
            DomainTransfer.initiated_at,
            DomainTransfer.completed_at,
            DomainTransfer.notes,
            DomainTransfer.created_at,
            Domain.domain_name,
            PlatformAccount.platform,
        )
        .outerjoin(Domain, Domain.id == DomainTransfer.domain_id)
        .outerjoin(PlatformAccount, PlatformAccount.id == DomainTransfer.from_account_id)
    )

    count_query = select(func.count(DomainTransfer.id))

    if status:
        query = query.where(DomainTransfer.status == status)
        count_query = count_query.where(DomainTransfer.status == status)

    if domain_id:
        query = query.where(DomainTransfer.domain_id == domain_id)
        count_query = count_query.where(DomainTransfer.domain_id == domain_id)

    if from_platform:
        query = query.where(PlatformAccount.platform == from_platform)
        count_query = count_query.where(PlatformAccount.platform == from_platform)

    if to_platform:
        query = query.where(DomainTransfer.to_platform == to_platform)
        count_query = count_query.where(DomainTransfer.to_platform == to_platform)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(DomainTransfer.initiated_at.desc())
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "domain_id": row.domain_id,
            "domain_name": row.domain_name,
            "from_platform": row.platform,
            "from_account_id": row.from_account_id,
            "to_platform": row.to_platform,
            "to_account": row.to_account,
            "status": row.status,
            "auth_code": row.auth_code,
            "initiated_at": row.initiated_at,
            "completed_at": row.completed_at,
            "notes": row.notes,
            "created_at": row.created_at,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_transfer(db: AsyncSession, transfer_id: int) -> dict | None:
    result = await db.execute(
        select(
            DomainTransfer.id,
            DomainTransfer.domain_id,
            DomainTransfer.from_account_id,
            DomainTransfer.to_platform,
            DomainTransfer.to_account,
            DomainTransfer.status,
            DomainTransfer.auth_code,
            DomainTransfer.initiated_at,
            DomainTransfer.completed_at,
            DomainTransfer.notes,
            DomainTransfer.created_at,
            Domain.domain_name,
            PlatformAccount.platform,
        )
        .outerjoin(Domain, Domain.id == DomainTransfer.domain_id)
        .outerjoin(PlatformAccount, PlatformAccount.id == DomainTransfer.from_account_id)
        .where(DomainTransfer.id == transfer_id)
    )
    row = result.one_or_none()
    if not row:
        return None

    return {
        "id": row.id,
        "domain_id": row.domain_id,
        "domain_name": row.domain_name,
        "from_platform": row.platform,
        "from_account_id": row.from_account_id,
        "to_platform": row.to_platform,
        "to_account": row.to_account,
        "status": row.status,
        "auth_code": row.auth_code,
        "initiated_at": row.initiated_at,
        "completed_at": row.completed_at,
        "notes": row.notes,
        "created_at": row.created_at,
    }


async def update_transfer_status(
    db: AsyncSession,
    transfer_id: int,
    status: str,
    notes: Optional[str] = None,
) -> DomainTransfer:
    result = await db.execute(
        select(DomainTransfer).where(DomainTransfer.id == transfer_id)
    )
    transfer = result.scalar_one()
    if not transfer:
        raise ValueError(f"Transfer {transfer_id} not found")

    transfer.status = status
    if notes:
        transfer.notes = notes

    if status in ("completed", "failed"):
        transfer.completed_at = datetime.utcnow()

    if status == "completed":
        result = await db.execute(
            select(Domain).where(Domain.id == transfer.domain_id)
        )
        domain = result.scalar_one()
        if domain:
            domain.status = "transferred"

    elif status == "failed":
        result = await db.execute(
            select(Domain).where(Domain.id == transfer.domain_id)
        )
        domain = result.scalar_one()
        if domain:
            domain.status = "active"

    await db.commit()
    await db.refresh(transfer)

    return transfer


async def cancel_transfer(
    db: AsyncSession,
    transfer_id: int,
) -> DomainTransfer:
    result = await db.execute(
        select(DomainTransfer).where(DomainTransfer.id == transfer_id)
    )
    transfer = result.scalar_one()
    if not transfer:
        raise ValueError(f"Transfer {transfer_id} not found")

    transfer.status = "cancelled"
    transfer.completed_at = datetime.utcnow()

    result = await db.execute(
        select(Domain).where(Domain.id == transfer.domain_id)
    )
    domain = result.scalar_one()
    if domain:
        domain.status = "active"

    await db.commit()
    await db.refresh(transfer)

    return transfer
