from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_no: str
    source: str
    requester_user_id: int
    requester_name: str | None
    operation_type: str
    target_type: str
    target_id: int | None
    domain_id: int | None
    payload: dict[str, Any]
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    risk_level: str
    status: str
    approval_channel: str
    approver_user_id: int | None
    approver_name: str | None
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    executed_at: datetime | None
    execution_result: dict[str, Any]
    error_message: str | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChangeRequestRejectBody(BaseModel):
    reason: str


class ChangeRequestListResponse(BaseModel):
    items: list[ChangeRequestResponse]
    total: int
    page: int
    page_size: int
