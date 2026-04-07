from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, and_, cast, false, or_

from app.models.domain import Domain
from app.models.platform_account import PlatformAccount

MANAGED_NS_PATTERNS: dict[str, tuple[str, ...]] = {
    "cloudflare": ("cloudflare.com",),
    "godaddy": ("domaincontrol.com",),
    "namecom": ("name.com",),
}


def is_non_expired_domain(domain: Domain, now: datetime | None = None) -> bool:
    current = now or datetime.utcnow()
    return bool(domain.expiry_date and domain.expiry_date > current and domain.status != "removed")


def is_dns_managed_by_account(domain: Domain, platform: str | None = None, now: datetime | None = None) -> bool:
    if not is_non_expired_domain(domain, now=now):
        return False

    current_platform = (platform or getattr(domain.account, "platform", None) or "").lower()
    patterns = MANAGED_NS_PATTERNS.get(current_platform)
    if not patterns:
        return False

    nameservers = domain.nameservers or []
    normalized = [str(item).lower() for item in nameservers if item]
    if not normalized:
        return False

    return any(any(pattern in ns for pattern in patterns) for ns in normalized)


def non_expired_domain_clause(now: datetime | None = None):
    current = now or datetime.utcnow()
    return and_(
        Domain.status != "removed",
        Domain.expiry_date.is_not(None),
        Domain.expiry_date > current,
    )


def dns_manageable_clause(now: datetime | None = None):
    nameservers_text = cast(Domain.nameservers, String)
    platform_rules = []
    for platform, patterns in MANAGED_NS_PATTERNS.items():
        pattern_clauses = [nameservers_text.ilike(f"%{pattern}%") for pattern in patterns]
        platform_rules.append(
            and_(
                PlatformAccount.platform == platform,
                or_(*pattern_clauses),
            )
        )

    if not platform_rules:
        return false()

    return and_(
        non_expired_domain_clause(now=now),
        or_(*platform_rules),
    )
