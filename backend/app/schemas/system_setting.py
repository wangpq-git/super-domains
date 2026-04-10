from typing import Any

from pydantic import BaseModel, Field


class SystemSettingItem(BaseModel):
    key: str
    category: str
    label: str
    description: str | None = None
    value_type: str
    ui_type: str = "input"
    rows: int | None = None
    is_secret: bool
    restart_required: bool
    value: Any = None
    masked_value: str | None = None
    is_configured: bool = False
    source: str = "default"


class SystemSettingListResponse(BaseModel):
    items: list[SystemSettingItem]


class SystemSettingUpdateEntry(BaseModel):
    key: str
    value: Any = Field(default=None)


class SystemSettingUpdateRequest(BaseModel):
    items: list[SystemSettingUpdateEntry]


class SystemSettingPublicValue(BaseModel):
    key: str
    value: Any = None
    source: str = "default"


class SystemSettingPublicResponse(BaseModel):
    items: list[SystemSettingPublicValue]
