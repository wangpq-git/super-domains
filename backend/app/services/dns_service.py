import logging
from datetime import datetime

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.domain import Domain
from app.models.dns_record import DnsRecord
from app.adapters import get_adapter
from app.core.encryption import decrypt_credentials
from app.schemas.dns_record import DnsRecordCreate, DnsRecordUpdate

logger = logging.getLogger(__name__)


async def _get_domain_with_account(db: AsyncSession, domain_id: int) -> Domain | None:
    result = await db.execute(
        select(Domain).options(selectinload(Domain.account)).where(Domain.id == domain_id)
    )
    return result.scalar_one_or_none()


async def _get_dns_record_with_domain(db: AsyncSession, record_id: int) -> DnsRecord | None:
    result = await db.execute(
        select(DnsRecord).options(
            selectinload(DnsRecord.domain).selectinload(Domain.account)
        ).where(DnsRecord.id == record_id)
    )
    return result.scalar_one_or_none()


async def list_dns_records(db: AsyncSession, domain_id: int) -> list[DnsRecord]:
    result = await db.execute(
        select(DnsRecord)
        .where(DnsRecord.domain_id == domain_id)
        .order_by(DnsRecord.record_type, DnsRecord.name)
    )
    return list(result.scalars().all())


async def sync_dns_records(db: AsyncSession, domain_id: int) -> dict:
    domain = await _get_domain_with_account(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter = get_adapter(account.platform, credentials)

    try:
        async with adapter:
            records_info = await adapter.list_dns_records(domain.domain_name)
    except Exception as e:
        logger.error("Failed to sync DNS for %s: %s", domain.domain_name, e)
        raise

    # Delete all existing records for this domain, then re-insert
    await db.execute(sa_delete(DnsRecord).where(DnsRecord.domain_id == domain_id))

    upserted = 0
    for rec in records_info:
        db.add(DnsRecord(
            domain_id=domain_id,
            record_type=rec.record_type,
            name=rec.name,
            content=rec.content,
            ttl=rec.ttl,
            priority=rec.priority,
            proxied=rec.proxied,
            external_id=rec.external_id,
            sync_status="synced",
            raw_data=rec.raw_data,
        ))
        upserted += 1

    await db.commit()

    return {
        "domain_id": domain_id,
        "domain_name": domain.domain_name,
        "upserted": upserted,
        "removed": 0,
    }


async def create_dns_record(db: AsyncSession, domain_id: int, data: DnsRecordCreate) -> DnsRecord:
    domain = await _get_domain_with_account(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    from app.adapters.base import DnsRecordInfo
    record_info = DnsRecordInfo(
        record_type=data.record_type, name=data.name, content=data.content,
        ttl=data.ttl or 3600, priority=data.priority, proxied=data.proxied,
    )

    adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
    async with adapter:
        external_id = await adapter.create_dns_record(domain.domain_name, record_info)

    record = DnsRecord(
        domain_id=domain_id, record_type=data.record_type, name=data.name,
        content=data.content, ttl=data.ttl or 3600, priority=data.priority,
        proxied=data.proxied, external_id=external_id, sync_status="synced",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_dns_record(db: AsyncSession, record_id: int, data: DnsRecordUpdate) -> DnsRecord:
    record = await _get_dns_record_with_domain(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return record

    from app.adapters.base import DnsRecordInfo
    record_info = DnsRecordInfo(
        record_type=record.record_type, name=record.name,
        content=update_fields.get("content", record.content),
        ttl=update_fields.get("ttl", record.ttl),
        priority=update_fields.get("priority", record.priority),
        proxied=update_fields.get("proxied", record.proxied),
    )

    if not record.external_id:
        raise ValueError("Cannot update DNS record without external_id")

    domain = record.domain
    adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
    async with adapter:
        await adapter.update_dns_record(domain.domain_name, record.external_id, record_info)

    for key, value in update_fields.items():
        setattr(record, key, value)
    await db.commit()
    await db.refresh(record)
    return record


async def delete_dns_record(db: AsyncSession, record_id: int) -> bool:
    record = await _get_dns_record_with_domain(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    if record.external_id:
        domain = record.domain
        adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
        async with adapter:
            await adapter.delete_dns_record(domain.domain_name, record.external_id)

    await db.delete(record)
    await db.commit()
    return True
