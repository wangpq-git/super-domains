from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    actor_name: str | None = None
    action: str
    target_type: str | None
    target_id: int | None
    domain_name: str | None = None
    detail: dict[str, Any]
    ip_address: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
