"""Public contracts for the governed coding workbench."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import UTCModel


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


class WorkbenchModel(UTCModel):
    model_config = ConfigDict(
        alias_generator=_camel_case, populate_by_name=True, from_attributes=True
    )


class WorkbenchRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel_case,
        extra="forbid",
        populate_by_name=True,
    )


class WorkbenchRepositoryRead(WorkbenchModel):
    id: str
    name: str
    default_ref: str


class WorkbenchRuntimeRead(WorkbenchModel):
    id: str
    name: str
    published_version: int
    runtime_type: str
    readiness: Literal["ready", "blocked"] = "ready"
    reason_code: str | None = None
    reason: str | None = None


class WorkbenchTestEvidence(WorkbenchRequest):
    command: str = Field(min_length=1, max_length=2000)
    outcome: Literal["passed", "failed", "unknown"]
    summary: str = Field(default="", max_length=8000)


class WorkbenchProposalRead(WorkbenchModel):
    id: str
    status: Literal["pending_confirmation", "applied", "failed", "cancelled"]
    base_sha: str
    checkpoint_sha: str
    diff: str
    modified_files: list[str]
    tests: list[WorkbenchTestEvidence]
    error_message: str | None = None
    confirmed_at: datetime | None = None


class WorkbenchTurnOutput(WorkbenchModel):
    modified_files: list[str] = Field(default_factory=list)
    tests: list[WorkbenchTestEvidence] = Field(default_factory=list)
    diff: str = ""
    proposal: WorkbenchProposalRead | None = None


class WorkbenchTurnRead(WorkbenchModel):
    id: str
    sequence: int
    request_id: str
    requirement: str
    runtime_id: str
    published_version: int
    runtime_type: str
    status: Literal["queued", "running", "proposed", "applied", "failed", "cancelled"]
    base_sha: str
    output: WorkbenchTurnOutput | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkbenchThreadRead(WorkbenchModel):
    id: str
    repository_id: str
    title: str | None = None
    status: Literal["active", "closed"]
    created_at: datetime
    updated_at: datetime
    turns: list[WorkbenchTurnRead] = Field(default_factory=list)


class WorkbenchEventRead(WorkbenchModel):
    id: str
    sequence: int = Field(ge=1)
    event_type: Literal[
        "started",
        "text",
        "tool_call",
        "tool_result",
        "state",
        "proposal",
        "done",
        "error",
        "cancelled",
    ]
    payload: dict[str, Any]
    created_at: datetime


class WorkbenchThreadSnapshot(WorkbenchModel):
    thread: WorkbenchThreadRead
    events: list[WorkbenchEventRead] = Field(default_factory=list)


class WorkbenchThreadCreate(WorkbenchRequest):
    repository_id: str = Field(min_length=1, max_length=36)
    runtime_id: str = Field(min_length=1, max_length=36)
    requirement: str = Field(min_length=1, max_length=20_000)
    request_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=255)


class WorkbenchTurnCreate(WorkbenchRequest):
    runtime_id: str = Field(min_length=1, max_length=36)
    requirement: str = Field(min_length=1, max_length=20_000)
    request_id: str = Field(min_length=1, max_length=64)
