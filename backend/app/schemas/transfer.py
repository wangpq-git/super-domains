from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TransferCreate(BaseModel):
    domain_id: int
    to_platform: str
    to_account: str = ""


class TransferUpdate(BaseModel):
    status: str
    notes: str | None = None


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    domain_id: int
    domain_name: str | None = None
    from_platform: str | None = None
    from_account_id: int | None
    to_platform: str
    to_account: str
    status: str
    auth_code: str | None
    initiated_at: datetime
    completed_at: datetime | None
    notes: str | None
    created_at: datetime | None = None


class TransferListResponse(BaseModel):
    items: list[TransferResponse]
    total: int
    page: int
    page_size: int
