from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.automation_schedule import parse_automation_schedule, parse_automation_timezone
from backend.schemas.common import UTCModel

SessionMode = Literal["fresh", "reuse"]
ApprovalMode = Literal["observe_only", "suggest_changes", "low_risk_automatic"]
StarterKey = Literal["daily-run-brief", "weekly-system-review", "anomaly-follow-up"]
STARTER_KEYS: tuple[str, ...] = (
    "daily-run-brief",
    "weekly-system-review",
    "anomaly-follow-up",
)

class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=20000)
    precheck: str | None = Field(default=None, max_length=4000)
    executor: str = Field(min_length=1, max_length=64)
    schedule: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    session_mode: SessionMode = "fresh"
    approval_mode: ApprovalMode = "suggest_changes"
    project: dict = Field(default_factory=dict)
    enabled: bool = True
    starter_key: StarterKey | None = None

class AutomationUpdate(BaseModel):
    operations_agent_id: str | None = None
    operations_agent_version: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    prompt: str | None = Field(default=None, min_length=1, max_length=20000)
    precheck: str | None = Field(default=None, max_length=4000)
    executor: str | None = Field(default=None, min_length=1, max_length=64)
    schedule: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    session_mode: SessionMode | None = None
    approval_mode: ApprovalMode | None = None
    project: dict | None = None
    enabled: bool | None = None

    @field_validator("schedule")
    @classmethod
    def updated_schedule_is_supported(cls, value: str | None) -> str | None:
        if value is not None:
            parse_automation_schedule(value)
        return value

    @field_validator("timezone")
    @classmethod
    def updated_timezone_is_supported(cls, value: str | None) -> str | None:
        if value is not None:
            parse_automation_timezone(value)
        return value

    @model_validator(mode="after")
    def updated_agent_binding_is_paired(self):
        fields = self.model_fields_set
        binding_fields = {"operations_agent_id", "operations_agent_version"}
        if fields & binding_fields and not binding_fields <= fields:
            raise ValueError("operations_agent_id and operations_agent_version must be updated together")
        if binding_fields <= fields and (
            (self.operations_agent_id is None) != (self.operations_agent_version is None)
        ):
            raise ValueError("operations_agent_id and operations_agent_version must both be set or null")
        return self


class AutomationRead(UTCModel):
    id: str
    workspace_id: str
    starter_key: StarterKey | None
    name: str
    prompt: str
    precheck: str | None
    executor: str
    schedule: str
    timezone: str
    session_mode: str
    approval_mode: str
    project: dict
    enabled: bool
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StarterPreviewItem(BaseModel):
    key: StarterKey
    name: str
    installed: bool
    automation_id: str | None = None


class StarterInstallationPreview(BaseModel):
    workspace_id: str
    starters: list[StarterPreviewItem]
    missing_count: int
    installed_count: int


class StarterInstallationResult(StarterInstallationPreview):
    created_count: int
    skipped_count: int

    model_config = {"from_attributes": True}
