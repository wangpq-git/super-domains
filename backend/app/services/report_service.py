from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount
from app.models.audit_log import AuditLog


def _get_month_key(d: datetime) -> str:
    return d.strftime("%Y-%m")


def get_overview(db: Session):
    total_domains = db.query(func.count(Domain.id)).scalar() or 0
    total_accounts = db.query(func.count(PlatformAccount.id)).scalar() or 0
    total_platforms = (
        db.query(func.count(func.distinct(PlatformAccount.platform))).scalar() or 0
    )

    status_counts = (
        db.query(Domain.status, func.count(Domain.id))
        .group_by(Domain.status)
        .all()
    )
    domains_by_status = {row[0]: row[1] for row in status_counts}

    platform_counts = (
        db.query(PlatformAccount.platform, func.count(Domain.id))
        .join(Domain, PlatformAccount.id == Domain.account_id)
        .group_by(PlatformAccount.platform)
        .all()
    )
    domains_by_platform = {row[0]: row[1] for row in platform_counts}

    now = datetime.utcnow()
    expiry_timeline = []
    for i in range(12):
        month_start = (now.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        month_key = _get_month_key(month_start)
        next_month_start = (month_start + timedelta(days=32)).replace(day=1)
        count = (
            db.query(func.count(Domain.id))
            .filter(
                Domain.expiry_date >= month_start,
                Domain.expiry_date < next_month_start,
            )
            .scalar()
            or 0
        )
        expiry_timeline.append({"month": month_key, "count": count})

    recent_syncs = (
        db.query(
            PlatformAccount.id,
            PlatformAccount.platform,
            PlatformAccount.account_name,
            PlatformAccount.last_sync_at,
            PlatformAccount.sync_status,
            PlatformAccount.sync_error,
        )
        .filter(PlatformAccount.last_sync_at.isnot(None))
        .order_by(PlatformAccount.last_sync_at.desc())
        .limit(10)
        .all()
    )
    recent_syncs_list = [
        {
            "account_id": row.id,
            "platform": row.platform,
            "account_name": row.account_name,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "sync_status": row.sync_status,
            "sync_error": row.sync_error,
        }
        for row in recent_syncs
    ]

    return {
        "total_domains": total_domains,
        "total_accounts": total_accounts,
        "total_platforms": total_platforms,
        "domains_by_status": domains_by_status,
        "domains_by_platform": domains_by_platform,
        "expiry_timeline": expiry_timeline,
        "recent_syncs": recent_syncs_list,
    }


def get_expiry_report(db: Session, days: int = 90):
    now = datetime.utcnow()
    deadline = now + timedelta(days=days)

    domains = (
        db.query(
            Domain.domain_name,
            PlatformAccount.platform,
            PlatformAccount.account_name,
            Domain.expiry_date,
        )
        .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
        .filter(
            Domain.expiry_date >= now,
            Domain.expiry_date <= deadline,
        )
        .order_by(Domain.expiry_date.asc())
        .all()
    )

    critical = []
    warning = []
    notice = []

    for row in domains:
        days_left = (row.expiry_date - now).days
        item = {
            "domain_name": row.domain_name,
            "platform": row.platform,
            "account": row.account_name,
            "expiry_date": row.expiry_date.strftime("%Y-%m-%d"),
            "days_left": days_left,
        }
        if days_left < 7:
            critical.append(item)
        elif days_left <= 30:
            warning.append(item)
        else:
            notice.append(item)

    return {
        "critical": critical,
        "warning": warning,
        "notice": notice,
        "total": len(critical) + len(warning) + len(notice),
    }


def get_platform_report(db: Session):
    platforms = db.query(PlatformAccount.platform).distinct().all()
    report = []
    now = datetime.utcnow()

    for (platform,) in platforms:
        domain_count = (
            db.query(func.count(Domain.id))
            .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
            .filter(PlatformAccount.platform == platform)
            .scalar()
            or 0
        )

        avg_expiry = None
        if domain_count > 0:
            avg_expiry_val = (
                db.query(func.avg(func.julianday(Domain.expiry_date)))
                .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
                .filter(PlatformAccount.platform == platform)
                .scalar()
            )
            if avg_expiry_val:
                avg_expiry = datetime.fromordinal(1721424 + int(avg_expiry_val)).strftime("%Y-%m-%d")

        auto_renew_total = (
            db.query(func.count(Domain.id))
            .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
            .filter(PlatformAccount.platform == platform)
            .scalar()
            or 0
        )
        auto_renew_count = (
            db.query(func.count(Domain.id))
            .join(PlatformAccount, Domain.account_id == PlatformAccount.id)
            .filter(PlatformAccount.platform == platform, Domain.auto_renew == True)
            .scalar()
            or 0
        )
        auto_renew_rate = round(auto_renew_count / auto_renew_total, 2) if auto_renew_total > 0 else 0.0

        accounts = (
            db.query(PlatformAccount)
            .filter(PlatformAccount.platform == platform)
            .all()
        )
        total_syncs = len([a for a in accounts if a.last_sync_at is not None])
        success_syncs = len([a for a in accounts if a.sync_status == "success"])
        sync_success_rate = round(success_syncs / total_syncs, 2) if total_syncs > 0 else 0.0

        report.append(
            {
                "platform": platform,
                "domain_count": domain_count,
                "avg_expiry": avg_expiry,
                "auto_renew_rate": auto_renew_rate,
                "sync_success_rate": sync_success_rate,
            }
        )

    return report
