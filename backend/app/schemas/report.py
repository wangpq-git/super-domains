from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_domains: int
    total_accounts: int
    total_platforms: int
    domains_by_status: dict
    domains_by_platform: dict
    expiry_timeline: list[dict]
    recent_syncs: list[dict]


class ExpiryReportItem(BaseModel):
    domain_name: str
    platform: str
    account: str
    expiry_date: str
    days_left: int


class ExpiryReport(BaseModel):
    critical: list[ExpiryReportItem]
    warning: list[ExpiryReportItem]
    notice: list[ExpiryReportItem]
    total: int


class PlatformReportItem(BaseModel):
    platform: str
    domain_count: int
    avg_expiry: Optional[str]
    auto_renew_rate: float
    sync_success_rate: float


class PlatformReport(BaseModel):
    items: list[PlatformReportItem]


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    username: str | None = None
    action: str
    target_type: str | None
    target_id: int | None
    detail: dict
    ip_address: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
