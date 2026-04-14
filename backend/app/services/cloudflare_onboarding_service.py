from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters import get_adapter
from app.core.encryption import decrypt_credentials
from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services import audit_log_service

CLOUDFLARE_PLATFORM = 'cloudflare'
DYNADOT_PLATFORM = 'dynadot'
CLOUDFLARE_ACCOUNT_LIMIT = 85

CACHE_RULE_NAME = 'cache everything'
CACHE_RULE_EXPRESSION = '(not starts_with(http.request.uri.path, "/api/")) or (not starts_with(http.request.uri.path, "/wp-"))'
CACHE_RULE_SETTINGS = {
    'cache': True,
    'edge_ttl': {
        'mode': 'override_origin',
        'default': 86400,
    },
    'browser_ttl': {
        'mode': 'override_origin',
        'default': 43200,
    },
    'cache_key': {
        'ignore_query_strings_order': False,
        'cache_deception_armor': False,
        'cache_by_device_type': True,
        'custom_key': {
            'query_string': {
                'exclude': [],
            },
            'user': {
                'device_type': True,
            },
            'header': {
                'include': [],
                'check_presence': [],
                'exclude_origin': False,
            },
            'host': {
                'resolved': False,
            },
            'cookie': {
                'include': [],
            },
        },
    },
}
CACHE_RULE_SNAPSHOT = {
    'name': CACHE_RULE_NAME,
    'expression': CACHE_RULE_EXPRESSION,
    'cache_eligibility': '符合缓存条件',
    'edge_ttl': '1天',
    'browser_ttl': '12小时',
    'cache_deception_armor': False,
    'cache_by_device_type': True,
    'ignore_query_strings': False,
    'query_string_sort': False,
    'position': 'first',
}


async def get_domain_for_onboarding(db: AsyncSession, domain_id: int) -> Domain | None:
    result = await db.execute(
        select(Domain)
        .options(selectinload(Domain.account))
        .where(Domain.id == domain_id)
    )
    return result.scalar_one_or_none()


async def select_target_cloudflare_account(db: AsyncSession) -> tuple[PlatformAccount, int]:
    domain_count = func.count(Domain.id)
    result = await db.execute(
        select(PlatformAccount, domain_count.label('domain_count'))
        .outerjoin(
            Domain,
            (Domain.account_id == PlatformAccount.id) & (Domain.status != 'removed'),
        )
        .where(
            PlatformAccount.platform == CLOUDFLARE_PLATFORM,
            PlatformAccount.is_active.is_(True),
        )
        .group_by(PlatformAccount.id)
        .having(domain_count <= CLOUDFLARE_ACCOUNT_LIMIT)
        .order_by(domain_count.asc(), PlatformAccount.id.asc())
    )
    row = result.first()
    if not row:
        raise ValueError('cloudflare 额度不足')
    account, count = row
    return account, int(count or 0)


async def ensure_onboardable_domain(db: AsyncSession, domain_id: int) -> Domain:
    domain = await get_domain_for_onboarding(db, domain_id)
    if not domain:
        raise ValueError(f'Domain {domain_id} not found')
    if not domain.account or str(domain.account.platform).lower() != DYNADOT_PLATFORM:
        raise ValueError('仅支持将 Dynadot 域名接入 Cloudflare')
    if domain.status == 'removed':
        raise ValueError('已移除域名不支持接入 Cloudflare')

    existing = await db.execute(
        select(Domain.id, PlatformAccount.account_name)
        .join(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(
            Domain.id != domain.id,
            Domain.domain_name == domain.domain_name,
            Domain.status != 'removed',
            PlatformAccount.platform == CLOUDFLARE_PLATFORM,
        )
    )
    duplicate = existing.first()
    if duplicate:
        raise ValueError(f'域名已存在于 Cloudflare 账户: {duplicate.account_name or duplicate.id}')
    return domain


async def execute_domain_onboard(
    db: AsyncSession,
    *,
    domain_id: int,
    target_account_id: int,
    audit_user_id: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    domain = await ensure_onboardable_domain(db, domain_id)
    target_account = await db.get(PlatformAccount, target_account_id)
    if not target_account or not target_account.is_active or target_account.platform != CLOUDFLARE_PLATFORM:
        raise ValueError('目标 Cloudflare 账户不可用')

    source_credentials = decrypt_credentials(domain.account.credentials)
    target_credentials = decrypt_credentials(target_account.credentials)

    async with get_adapter(target_account.platform, target_credentials) as cloudflare_adapter:
        zone = await cloudflare_adapter.create_zone(domain.domain_name)
        zone_id = zone.get('id')
        nameservers = [ns.strip().lower() for ns in zone.get('name_servers') or [] if str(ns).strip()]
        if not zone_id:
            raise ValueError('Cloudflare zone 创建失败')
        if len(nameservers) < 2:
            raise ValueError('Cloudflare 未返回完整 NS')
        cache_rule = await cloudflare_adapter.ensure_cache_rule(
            zone_id,
            rule_name=CACHE_RULE_NAME,
            expression=CACHE_RULE_EXPRESSION,
            settings=CACHE_RULE_SETTINGS,
            position='first',
        )

    async with get_adapter(domain.account.platform, source_credentials) as dynadot_adapter:
        await dynadot_adapter.update_nameservers(domain.domain_name, nameservers)

    now = datetime.now(UTC).replace(tzinfo=None)
    previous_account_id = domain.account_id
    previous_account_name = domain.account.account_name if domain.account else None
    previous_platform = domain.account.platform if domain.account else DYNADOT_PLATFORM
    previous_nameservers = list(domain.nameservers or [])
    previous_raw = domain.raw_data if isinstance(domain.raw_data, dict) else {}
    domain.account_id = target_account.id
    domain.external_id = zone_id
    domain.nameservers = nameservers
    domain.status = zone.get('status') or domain.status or 'active'
    domain.last_synced_at = now
    domain.raw_data = {
        **previous_raw,
        'onboarded_from_platform': previous_platform,
        'onboarded_from_account_id': previous_account_id,
        'cloudflare_zone': zone,
        'cloudflare_cache_rule': cache_rule,
        'dynadot_nameserver_update': {
            'nameservers': nameservers,
            'updated_at': now.isoformat(),
        },
    }

    if audit_user_id is not None:
        await audit_log_service.add_audit_log(
            db,
            user_id=audit_user_id,
            action='domain.cloudflare_onboard',
            target_type='domain',
            target_id=domain.id,
            detail={
                'domain_id': domain.id,
                'domain_name': domain.domain_name,
                'before': {
                    'platform': previous_platform,
                    'account_id': previous_account_id,
                    'account_name': previous_account_name,
                    'nameservers': previous_nameservers,
                },
                'after': {
                    'platform': CLOUDFLARE_PLATFORM,
                    'account_id': target_account.id,
                    'account_name': target_account.account_name,
                    'nameservers': nameservers,
                    'zone_id': zone_id,
                    'cache_rule': CACHE_RULE_SNAPSHOT,
                },
                'cache_rule': CACHE_RULE_SNAPSHOT,
                **(audit_context or {}),
            },
        )

    await db.commit()
    await db.refresh(domain)

    return {
        'domain_id': domain.id,
        'domain_name': domain.domain_name,
        'target_account_id': target_account.id,
        'target_account_name': target_account.account_name,
        'zone_id': zone_id,
        'nameservers': nameservers,
        'cache_rule': cache_rule,
    }
