import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services.dns_eligibility import dns_manageable_clause, non_expired_domain_clause

logger = logging.getLogger(__name__)


async def list_domains(
    db: AsyncSession,
    *,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    expiry_start: Optional[str] = None,
    expiry_end: Optional[str] = None,
    exclude_expired: bool = False,
    dns_manageable_only: bool = False,
    sort_by: str = "expiry_date",
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = (
        select(
            Domain.id,
            Domain.account_id,
            Domain.domain_name,
            Domain.tld,
            Domain.status,
            Domain.registration_date,
            Domain.expiry_date,
            Domain.auto_renew,
            Domain.locked,
            Domain.whois_privacy,
            Domain.nameservers,
            Domain.external_id,
            Domain.last_synced_at,
            Domain.created_at,
            PlatformAccount.platform,
            PlatformAccount.account_name,
        )
        .outerjoin(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(Domain.status != "removed")
    )

    count_query = (
        select(func.count(Domain.id))
        .outerjoin(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(Domain.status != "removed")
    )

    if platform:
        query = query.where(PlatformAccount.platform == platform)
        count_query = count_query.where(PlatformAccount.platform == platform)

    if status:
        query = query.where(Domain.status == status)
        count_query = count_query.where(Domain.status == status)

    if search:
        like_pattern = f"%{search}%"
        query = query.where(Domain.domain_name.ilike(like_pattern))
        count_query = count_query.where(Domain.domain_name.ilike(like_pattern))

    if expiry_start:
        query = query.where(Domain.expiry_date >= expiry_start)
        count_query = count_query.where(Domain.expiry_date >= expiry_start)

    if expiry_end:
        query = query.where(Domain.expiry_date <= expiry_end)
        count_query = count_query.where(Domain.expiry_date <= expiry_end)

    if exclude_expired:
        clause = non_expired_domain_clause()
        query = query.where(clause)
        count_query = count_query.where(clause)

    if dns_manageable_only:
        clause = dns_manageable_clause()
        query = query.where(clause)
        count_query = count_query.where(clause)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    ALLOWED_SORT_FIELDS = {"domain_name", "expiry_date", "status", "created_at", "registration_date", "tld"}
    if sort_by in ALLOWED_SORT_FIELDS:
        col = getattr(Domain, sort_by)
        query = query.order_by(col.desc() if sort_order == "desc" else col.asc())
    else:
        query = query.order_by(Domain.expiry_date.asc())

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "account_id": row.account_id,
            "domain_name": row.domain_name,
            "tld": row.tld,
            "status": row.status,
            "registration_date": row.registration_date,
            "expiry_date": row.expiry_date,
            "auto_renew": row.auto_renew,
            "locked": row.locked,
            "whois_privacy": row.whois_privacy,
            "nameservers": row.nameservers,
            "external_id": row.external_id,
            "last_synced_at": row.last_synced_at,
            "platform": row.platform,
            "account": row.account_name,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_domain_stats(db: AsyncSession) -> dict:
    now = datetime.now(UTC).replace(tzinfo=None)
    thirty_days_later = now + __import__("datetime").timedelta(days=30)
    seven_days_later = now + __import__("datetime").timedelta(days=7)

    total_result = await db.execute(
        select(func.count(Domain.id)).where(Domain.status != "removed")
    )
    total = total_result.scalar() or 0

    expiring_result = await db.execute(
        select(func.count(Domain.id)).where(
            Domain.status != "removed",
            Domain.expiry_date > now,
            Domain.expiry_date <= thirty_days_later,
        )
    )
    expiring_soon = expiring_result.scalar() or 0

    expired_result = await db.execute(
        select(func.count(Domain.id)).where(
            Domain.status != "removed",
            Domain.expiry_date <= now,
        )
    )
    expired = expired_result.scalar() or 0

    platform_result = await db.execute(
        select(PlatformAccount.platform, func.count(Domain.id))
        .outerjoin(Domain, Domain.account_id == PlatformAccount.id)
        .where(Domain.status != "removed")
        .group_by(PlatformAccount.platform)
    )
    by_platform = {row[0]: row[1] for row in platform_result.all()}

    status_result = await db.execute(
        select(Domain.status, func.count(Domain.id))
        .where(Domain.status != "removed")
        .group_by(Domain.status)
    )
    by_status = {row[0]: row[1] for row in status_result.all()}

    expiry_buckets = {
        "已过期": 0,
        "7天内": 0,
        "30天内": 0,
        "30天后": 0,
    }
    expiry_result = await db.execute(
        select(Domain.expiry_date)
        .where(Domain.status != "removed")
    )
    for (expiry_date,) in expiry_result.all():
        if expiry_date and expiry_date <= now:
            expiry_buckets["已过期"] += 1
        elif expiry_date and expiry_date <= seven_days_later:
            expiry_buckets["7天内"] += 1
        elif expiry_date and expiry_date <= thirty_days_later:
            expiry_buckets["30天内"] += 1
        else:
            expiry_buckets["30天后"] += 1

    platform_count_result = await db.execute(
        select(func.count(PlatformAccount.id)).where(PlatformAccount.is_active == True)
    )
    platform_count = platform_count_result.scalar() or 0

    return {
        "total_domains": total,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "platform_count": platform_count,
        "by_platform": by_platform,
        "by_status": by_status,
        "by_expiry": expiry_buckets,
    }


async def get_domain_detail(db: AsyncSession, domain_id: int) -> dict | None:
    result = await db.execute(
        select(
            Domain.id,
            Domain.account_id,
            Domain.domain_name,
            Domain.tld,
            Domain.status,
            Domain.registration_date,
            Domain.expiry_date,
            Domain.auto_renew,
            Domain.locked,
            Domain.whois_privacy,
            Domain.nameservers,
            Domain.external_id,
            Domain.last_synced_at,
            Domain.created_at,
            PlatformAccount.platform,
            PlatformAccount.account_name,
        )
        .outerjoin(PlatformAccount, PlatformAccount.id == Domain.account_id)
        .where(Domain.id == domain_id)
    )
    row = result.one_or_none()
    if not row:
        return None

    return {
        "id": row.id,
        "account_id": row.account_id,
        "domain_name": row.domain_name,
        "tld": row.tld,
        "status": row.status,
        "registration_date": row.registration_date,
        "expiry_date": row.expiry_date,
        "auto_renew": row.auto_renew,
        "locked": row.locked,
        "whois_privacy": row.whois_privacy,
        "nameservers": row.nameservers,
        "external_id": row.external_id,
        "last_synced_at": row.last_synced_at,
        "platform": row.platform,
        "account": row.account_name,
    }
