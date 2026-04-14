import logging
from typing import Any

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters import get_adapter
from app.core.encryption import decrypt_credentials
from app.models.dns_record import DnsRecord
from app.models.domain import Domain
from app.schemas.dns_record import DnsRecordCreate, DnsRecordUpdate
from app.services import audit_log_service
from app.services.dns_eligibility import is_dns_managed_by_account
from app.services.dns_validation import validate_dns_record_fields

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


def _record_snapshot(record: DnsRecord | None) -> dict[str, Any]:
    if not record:
        return {}
    return {
        'record_type': record.record_type,
        'name': record.name,
        'content': record.content,
        'ttl': record.ttl,
        'priority': record.priority,
        'proxied': record.proxied,
        'external_id': record.external_id,
    }


async def _add_domain_audit_log(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    domain: Domain,
    target_type: str,
    target_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    extra_detail: dict[str, Any] | None = None,
) -> None:
    detail = {
        'domain_id': domain.id,
        'domain_name': domain.domain_name,
    }
    if before is not None:
        detail['before'] = before
    if after is not None:
        detail['after'] = after
    if extra_detail:
        detail.update(extra_detail)

    await audit_log_service.add_audit_log(
        db,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )


async def list_dns_records(
    db: AsyncSession,
    domain_id: int,
    *,
    sort_by: str = 'record_type',
    sort_order: str = 'asc',
) -> list[DnsRecord]:
    allowed_sort_fields = {'record_type', 'name', 'content', 'ttl'}
    query = select(DnsRecord).where(DnsRecord.domain_id == domain_id)
    if sort_by in allowed_sort_fields:
        col = getattr(DnsRecord, sort_by)
        query = query.order_by(col.desc() if sort_order == 'desc' else col.asc())
    else:
        query = query.order_by(DnsRecord.record_type.asc(), DnsRecord.name.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def sync_dns_records(db: AsyncSession, domain_id: int) -> dict:
    domain = await _get_domain_with_account(db, domain_id)
    if not domain:
        raise ValueError(f'Domain {domain_id} not found')
    if not is_dns_managed_by_account(domain):
        raise RuntimeError('当前域名未过期，但 NS 不在当前账户下，已跳过同步')

    account = domain.account
    credentials = decrypt_credentials(account.credentials)
    adapter = get_adapter(account.platform, credentials)

    try:
        async with adapter:
            records_info = await adapter.list_dns_records(domain.domain_name)
    except Exception as exc:
        logger.error('Failed to sync DNS for %s: %s', domain.domain_name, exc)
        raise

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
            sync_status='synced',
            raw_data=rec.raw_data,
        ))
        upserted += 1

    await db.commit()

    return {
        'domain_id': domain_id,
        'domain_name': domain.domain_name,
        'upserted': upserted,
        'removed': 0,
    }


async def create_dns_record(
    db: AsyncSession,
    domain_id: int,
    data: DnsRecordCreate,
    *,
    audit_user_id: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> DnsRecord:
    domain = await _get_domain_with_account(db, domain_id)
    if not domain:
        raise ValueError(f'Domain {domain_id} not found')
    normalized = validate_dns_record_fields(
        record_type=data.record_type,
        name=data.name,
        content=data.content,
        ttl=data.ttl or 3600,
        priority=data.priority,
        proxied=data.proxied,
    )

    from app.adapters.base import DnsRecordInfo

    record_info = DnsRecordInfo(
        record_type=normalized['record_type'],
        name=normalized['name'],
        content=normalized['content'],
        ttl=normalized['ttl'] or 3600,
        priority=normalized['priority'],
        proxied=normalized['proxied'],
    )

    adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
    async with adapter:
        external_id = await adapter.create_dns_record(domain.domain_name, record_info)

    record = DnsRecord(
        domain_id=domain_id,
        record_type=normalized['record_type'],
        name=normalized['name'],
        content=normalized['content'],
        ttl=normalized['ttl'] or 3600,
        priority=normalized['priority'],
        proxied=normalized['proxied'],
        external_id=external_id,
        sync_status='synced',
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    if audit_user_id is not None:
        await _add_domain_audit_log(
            db,
            user_id=audit_user_id,
            action='dns.create',
            domain=domain,
            target_type='dns_record',
            target_id=record.id,
            after=_record_snapshot(record),
            extra_detail=audit_context,
        )
        await db.commit()

    return record


async def update_dns_record(
    db: AsyncSession,
    record_id: int,
    data: DnsRecordUpdate,
    *,
    audit_user_id: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> DnsRecord:
    record = await _get_dns_record_with_domain(db, record_id)
    if not record:
        raise ValueError(f'DNS record {record_id} not found')

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return record
    normalized = validate_dns_record_fields(
        record_type=record.record_type,
        name=record.name,
        content=update_fields.get('content', record.content),
        ttl=update_fields.get('ttl', record.ttl),
        priority=update_fields.get('priority', record.priority),
        proxied=update_fields.get('proxied', record.proxied),
    )

    before_snapshot = _record_snapshot(record)

    from app.adapters.base import DnsRecordInfo

    record_info = DnsRecordInfo(
        record_type=normalized['record_type'],
        name=normalized['name'],
        content=normalized['content'],
        ttl=normalized['ttl'],
        priority=normalized['priority'],
        proxied=normalized['proxied'],
    )

    if not record.external_id:
        raise ValueError('Cannot update DNS record without external_id')

    domain = record.domain
    adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
    async with adapter:
        await adapter.update_dns_record(domain.domain_name, record.external_id, record_info)

    for key, value in update_fields.items():
        if key in normalized:
            value = normalized[key]
        setattr(record, key, value)
    await db.commit()
    await db.refresh(record)

    if audit_user_id is not None:
        await _add_domain_audit_log(
            db,
            user_id=audit_user_id,
            action='dns.update',
            domain=domain,
            target_type='dns_record',
            target_id=record.id,
            before=before_snapshot,
            after=_record_snapshot(record),
            extra_detail=audit_context,
        )
        await db.commit()

    return record


async def delete_dns_record(
    db: AsyncSession,
    record_id: int,
    *,
    audit_user_id: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> bool:
    record = await _get_dns_record_with_domain(db, record_id)
    if not record:
        raise ValueError(f'DNS record {record_id} not found')

    domain = record.domain
    before_snapshot = _record_snapshot(record)

    if record.external_id:
        adapter = get_adapter(domain.account.platform, decrypt_credentials(domain.account.credentials))
        async with adapter:
            await adapter.delete_dns_record(domain.domain_name, record.external_id)

    await db.delete(record)
    await db.commit()

    if audit_user_id is not None:
        await _add_domain_audit_log(
            db,
            user_id=audit_user_id,
            action='dns.delete',
            domain=domain,
            target_type='dns_record',
            target_id=record_id,
            before=before_snapshot,
            extra_detail=audit_context,
        )
        await db.commit()

    return True
