from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class PlatformAccountCreate(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32)
    account_name: str | None = Field(None, max_length=100)
    credentials: dict
    config: dict = Field(default_factory=dict)


class PlatformAccountUpdate(BaseModel):
    account_name: str | None = Field(None, max_length=100)
    credentials: dict | None = None
    config: dict | None = None
    is_active: bool | None = None


class PlatformAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    account_name: str | None
    is_active: bool
    last_sync_at: datetime | None
    sync_status: str
    sync_error: str | None
    domain_count: int = 0
    created_at: datetime


class PlatformAccountListResponse(BaseModel):
    items: list[PlatformAccountResponse]
    total: int
    page: int
    page_size: int
