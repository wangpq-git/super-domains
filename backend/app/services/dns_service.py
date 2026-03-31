import logging
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.domain import Domain
from app.models.dns_record import DnsRecord
from app.adapters import get_adapter
from app.core.encryption import decrypt_credentials
from app.schemas.dns_record import DnsRecordCreate, DnsRecordUpdate

logger = logging.getLogger(__name__)


async def _get_domain(db: AsyncSession, domain_id: int) -> Domain | None:
    result = await db.execute(select(Domain).where(Domain.id == domain_id))
    return result.scalar_one_or_none()


async def _get_dns_record(db: AsyncSession, record_id: int) -> DnsRecord | None:
    result = await db.execute(select(DnsRecord).where(DnsRecord.id == record_id))
    return result.scalar_one_or_none()


async def list_dns_records(db: AsyncSession, domain_id: int) -> list[DnsRecord]:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    result = await db.execute(
        select(DnsRecord)
        .where(DnsRecord.domain_id == domain_id)
        .order_by(DnsRecord.record_type, DnsRecord.name)
    )
    return list(result.scalars().all())


async def sync_dns_records(db: AsyncSession, domain_id: int) -> dict:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter_cls = get_adapter(account.platform, credentials)

    try:
        async with adapter_cls:
            records_info = await adapter_cls.list_dns_records(domain.domain_name)
    except Exception as e:
        logger.error("Failed to sync DNS records for domain %s: %s", domain.domain_name, e)
        raise

    now = datetime.utcnow()
    seen_ids = set()
    upserted = 0

    for rec in records_info:
        eid = rec.external_id
        if eid:
            seen_ids.add(eid)

        stmt = pg_insert(DnsRecord).values(
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
        ).on_conflict_do_update(
            constraint="uq_dns_domain_external",
            set_={
                "record_type": rec.record_type,
                "name": rec.name,
                "content": rec.content,
                "ttl": rec.ttl,
                "priority": rec.priority,
                "proxied": rec.proxied,
                "sync_status": "synced",
                "raw_data": rec.raw_data,
                "updated_at": now,
            },
        ).on_conflict_do_nothing()

        try:
            await db.execute(stmt)
            upserted += 1
        except Exception:
            existing = await db.execute(
                select(DnsRecord).where(
                    DnsRecord.domain_id == domain_id,
                    DnsRecord.record_type == rec.record_type,
                    DnsRecord.name == rec.name,
                    DnsRecord.content == rec.content,
                )
            )
            existing_rec = existing.scalar_one_or_none()
            if not existing_rec:
                new_rec = DnsRecord(
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
                )
                db.add(new_rec)
                upserted += 1
            else:
                existing_rec.content = rec.content
                existing_rec.ttl = rec.ttl
                existing_rec.priority = rec.priority
                existing_rec.proxied = rec.proxied
                existing_rec.external_id = rec.external_id
                existing_rec.sync_status = "synced"
                existing_rec.updated_at = now
                upserted += 1

    removed_result = await db.execute(
        select(DnsRecord).where(
            DnsRecord.domain_id == domain_id,
            DnsRecord.sync_status == "synced",
        )
    )
    removed_count = 0
    for rec in removed_result.scalars().all():
        if rec.external_id and rec.external_id not in seen_ids:
            await db.delete(rec)
            removed_count += 1

    domain.last_synced_at = now
    await db.commit()

    logger.info(
        "Synced DNS records for domain %s: %d upserted, %d removed",
        domain.domain_name, upserted, removed_count,
    )

    return {
        "domain_id": domain_id,
        "domain_name": domain.domain_name,
        "upserted": upserted,
        "removed": removed_count,
    }


async def create_dns_record(db: AsyncSession, domain_id: int, data: DnsRecordCreate) -> DnsRecord:
    domain = await _get_domain(db, domain_id)
    if not domain:
        raise ValueError(f"Domain {domain_id} not found")

    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter_cls = get_adapter(account.platform, credentials)

    from app.adapters.base import DnsRecordInfo

    record_info = DnsRecordInfo(
        record_type=data.record_type,
        name=data.name,
        content=data.content,
        ttl=data.ttl or 3600,
        priority=data.priority,
        proxied=data.proxied,
    )

    async with adapter_cls:
        external_id = await adapter_cls.create_dns_record(domain.domain_name, record_info)

    record = DnsRecord(
        domain_id=domain_id,
        record_type=data.record_type,
        name=data.name,
        content=data.content,
        ttl=data.ttl or 3600,
        priority=data.priority,
        proxied=data.proxied,
        external_id=external_id,
        sync_status="synced",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def update_dns_record(db: AsyncSession, record_id: int, data: DnsRecordUpdate) -> DnsRecord:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    domain = record.domain
    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter_cls = get_adapter(account.platform, credentials)

    update_fields = data.model_dump(exclude_unset=True)

    if not update_fields:
        return record

    from app.adapters.base import DnsRecordInfo

    record_info = DnsRecordInfo(
        record_type=record.record_type,
        name=record.name,
        content=update_fields.get("content", record.content),
        ttl=update_fields.get("ttl", record.ttl),
        priority=update_fields.get("priority", record.priority),
        proxied=update_fields.get("proxied", record.proxied),
    )

    external_id = record.external_id
    if not external_id:
        raise ValueError("Cannot update DNS record without external_id")

    async with adapter_cls:
        await adapter_cls.update_dns_record(domain.domain_name, external_id, record_info)

    for key, value in update_fields.items():
        setattr(record, key, value)

    record.sync_status = "synced"
    record.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(record)
    return record


async def delete_dns_record(db: AsyncSession, record_id: int) -> bool:
    record = await _get_dns_record(db, record_id)
    if not record:
        raise ValueError(f"DNS record {record_id} not found")

    domain = record.domain
    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter_cls = get_adapter(account.platform, credentials)

    external_id = record.external_id
    if not external_id:
        await db.delete(record)
        await db.commit()
        return True

    async with adapter_cls:
        await adapter_cls.delete_dns_record(domain.domain_name, external_id)

    await db.delete(record)
    await db.commit()
    return True
