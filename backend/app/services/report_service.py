from datetime import datetime, timedelta

from sqlalchemy import select, func, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.services import data_cache_service, system_setting_service


async def get_overview(db: AsyncSession):
    ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key("report_overview")

    async def _load():
        total_domains = (await db.execute(select(func.count(Domain.id)))).scalar() or 0
        total_accounts = (await db.execute(select(func.count(PlatformAccount.id)))).scalar() or 0
        total_platforms = (await db.execute(select(func.count(distinct(PlatformAccount.platform))))).scalar() or 0

        status_rows = (await db.execute(
            select(Domain.status, func.count(Domain.id)).group_by(Domain.status)
        )).all()
        domains_by_status = {row[0]: row[1] for row in status_rows}

        platform_rows = (await db.execute(
            select(PlatformAccount.platform, func.count(Domain.id))
            .join(Domain, PlatformAccount.id == Domain.account_id)
            .group_by(PlatformAccount.platform)
        )).all()
        domains_by_platform = {row[0]: row[1] for row in platform_rows}

        now = datetime.utcnow()
        expiry_timeline = []
        for i in range(12):
            month_start = (now.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            month_key = month_start.strftime("%Y-%m")
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            count = (await db.execute(
                select(func.count(Domain.id)).where(
                    and_(Domain.expiry_date >= month_start, Domain.expiry_date < next_month)
                )
            )).scalar() or 0
            expiry_timeline.append({"month": month_key, "count": count})

        sync_rows = (await db.execute(
            select(
                PlatformAccount.id, PlatformAccount.platform, PlatformAccount.account_name,
                PlatformAccount.last_sync_at, PlatformAccount.sync_status, PlatformAccount.sync_error,
            )
            .where(PlatformAccount.last_sync_at.isnot(None))
            .order_by(PlatformAccount.last_sync_at.desc())
            .limit(10)
        )).all()
        recent_syncs = [
            {
                "account_id": r.id, "platform": r.platform, "account_name": r.account_name,
                "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
                "sync_status": r.sync_status, "sync_error": r.sync_error,
            }
            for r in sync_rows
        ]

        return {
            "total_domains": total_domains,
            "total_accounts": total_accounts,
            "total_platforms": total_platforms,
            "domains_by_status": domains_by_status,
            "domains_by_platform": domains_by_platform,
            "expiry_timeline": expiry_timeline,
            "recent_syncs": recent_syncs,
        }

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=ttl_seconds)


async def get_expiry_report(db: AsyncSession, days: int = 90):
    ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key("report_expiry", days=days)

    async def _load():
        now = datetime.utcnow()
        deadline = now + timedelta(days=days)

        rows = (await db.execute(
            select(Domain.domain_name, PlatformAccount.platform, PlatformAccount.account_name, Domain.expiry_date)
            .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
            .where(and_(Domain.expiry_date >= now, Domain.expiry_date <= deadline))
            .order_by(Domain.expiry_date.asc())
        )).all()

        critical, warning, notice = [], [], []
        for r in rows:
            days_left = (r.expiry_date - now).days
            item = {"domain_name": r.domain_name, "platform": r.platform, "account": r.account_name,
                    "expiry_date": r.expiry_date.strftime("%Y-%m-%d"), "days_left": days_left}
            if days_left < 7:
                critical.append(item)
            elif days_left <= 30:
                warning.append(item)
            else:
                notice.append(item)

        return {"critical": critical, "warning": warning, "notice": notice, "total": len(rows)}

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=ttl_seconds)


async def get_platform_report(db: AsyncSession):
    ttl_seconds = await system_setting_service.get_int(db, "DATA_CACHE_TTL_SECONDS")
    cache_key = data_cache_service.build_cache_key("report_platforms")

    async def _load():
        platforms = (await db.execute(select(distinct(PlatformAccount.platform)))).scalars().all()
        report = []

        for platform in platforms:
            domain_count = (await db.execute(
                select(func.count(Domain.id))
                .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
                .where(PlatformAccount.platform == platform)
            )).scalar() or 0

            auto_renew_count = (await db.execute(
                select(func.count(Domain.id))
                .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
                .where(PlatformAccount.platform == platform, Domain.auto_renew == True)
            )).scalar() or 0
            auto_renew_rate = round(auto_renew_count / domain_count, 2) if domain_count > 0 else 0.0

            report.append({
                "platform": platform,
                "domain_count": domain_count,
                "auto_renew_rate": auto_renew_rate,
            })

        return report

    return await data_cache_service.get_or_set(cache_key, _load, ttl_seconds=ttl_seconds)
