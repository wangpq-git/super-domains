from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DnsRecordCreate(BaseModel):
    record_type: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    ttl: int | None = 3600
    priority: int | None = None
    proxied: bool | None = None


class DnsRecordUpdate(BaseModel):
    content: str | None = None
    ttl: int | None = None
    priority: int | None = None
    proxied: bool | None = None


class DnsRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain_id: int
    record_type: str
    name: str
    content: str
    ttl: int
    priority: int | None
    proxied: bool | None
    external_id: str | None
    sync_status: str
    created_at: datetime
    updated_at: datetime
