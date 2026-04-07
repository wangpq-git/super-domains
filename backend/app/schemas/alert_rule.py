from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rule_type: str = Field(..., min_length=1, max_length=30)
    days_before: int | None = Field(None, ge=1, le=365)
    is_enabled: bool = True
    channels: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)
    apply_to_all: bool = True
    specific_platforms: list[str] | None = None
    specific_domains: list[int] | None = None
    excluded_platforms: list[str] = Field(default_factory=list)
    severity: str = Field(default="warning", pattern="^(urgent|warning|info)$")
    schedule: dict = Field(default_factory=lambda: {"type": "manual", "time": "09:00:00"})


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    rule_type: str | None = Field(None, min_length=1, max_length=30)
    days_before: int | None = Field(None, ge=1, le=365)
    is_enabled: bool | None = None
    channels: list[str] | None = None
    recipients: list[str] | None = None
    apply_to_all: bool | None = None
    specific_platforms: list[str] | None = None
    specific_domains: list[int] | None = None
    excluded_platforms: list[str] | None = None
    severity: str | None = Field(None, pattern="^(urgent|warning|info)$")
    schedule: dict | None = None


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: str
    days_before: int | None
    is_enabled: bool
    channels: list
    recipients: list
    apply_to_all: bool
    specific_platforms: list | None
    specific_domains: list | None
    excluded_platforms: list | None
    severity: str | None
    schedule: dict | None
    last_triggered_at: datetime | None
    created_at: datetime
