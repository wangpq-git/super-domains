from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    domain_name: str | None
    tld: str | None
    status: str
    registration_date: datetime | None
    expiry_date: datetime
    auto_renew: bool
    locked: bool
    whois_privacy: bool
    nameservers: list
    external_id: str | None
    last_synced_at: datetime | None
    platform: str | None = None
    account_name: str | None = None


class DomainListResponse(BaseModel):
    items: list[DomainResponse]
    total: int
    page: int
    page_size: int


class DomainStats(BaseModel):
    total_domains: int
    by_platform: dict
    by_status: dict
    expiring_30d: int
    expiring_7d: int
    expired: int
