"""Versioned, redacted contracts for the Admin-to-III collection vertical."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _V1Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class IIICollectionRequestV1(_V1Model):
    """Canonical collection intent, with no credential or endpoint fields."""

    site: str = Field(min_length=1, max_length=255)
    command: str = Field(min_length=1, max_length=255)
    args: dict = Field(default_factory=dict)
    output_format: str = Field(default="json", min_length=1, max_length=32)
    mode: str | None = Field(default=None, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_binding_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_binding_revision_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_binding_revision_number: int | None = Field(default=None, ge=1)


class IIICollectionSubmitV1(_V1Model):
    version: Literal["v1"] = "v1"
    idempotency_key: str = Field(min_length=1, max_length=255)
    node_id: str = Field(min_length=1, max_length=255)
    collection: IIICollectionRequestV1


class IIICollectionLifecycleSummaryV1(_V1Model):
    """Execution-only summary; ODP ingress receipts are deliberately out of scope."""

    items_fetched: int | None = Field(default=None, ge=0)


class IIICollectionLifecycleV1(_V1Model):
    version: Literal["v1"] = "v1"
    workspace_id: str = Field(min_length=1, max_length=36)
    project_id: str = Field(min_length=1, max_length=36)
    workflow_id: str = Field(min_length=1, max_length=36)
    studio_workflow_version_id: str = Field(min_length=1, max_length=36)
    run_id: str = Field(min_length=1, max_length=36)
    node_id: str = Field(min_length=1, max_length=255)
    command_id: str = Field(min_length=1, max_length=36)
    attempt_id: str = Field(min_length=1, max_length=36)
    attempt_number: int = Field(ge=1)
    task_id: str = Field(min_length=1, max_length=36)
    trace_id: str = Field(min_length=1, max_length=255)
    source_id: str = Field(min_length=1, max_length=36)
    source_binding_id: str | None = Field(default=None, max_length=36)
    source_binding_revision_id: str | None = Field(default=None, max_length=36)
    source_binding_revision_number: int | None = Field(default=None, ge=1)
    payload_sha256: str = Field(min_length=64, max_length=64)
    sequence: int = Field(ge=1)
    event_type: Literal["bridge_accepted", "collector_started", "collector_returned"]
    summary: IIICollectionLifecycleSummaryV1 = Field(default_factory=IIICollectionLifecycleSummaryV1)


class IIICollectionSubmitReadV1(_V1Model):
    version: Literal["v1"] = "v1"
    command_id: str
    attempt_id: str
    attempt_number: int
    task_id: str
    trace_id: str
    payload_sha256: str
    created: bool
    dispatch_state: str


class IIICollectionLifecycleReadV1(_V1Model):
    version: Literal["v1"] = "v1"
    command_id: str
    attempt_id: str
    sequence: int
    event_type: str
    duplicate: bool


class VerticalEvidenceReferenceV1(_V1Model):
    kind: Literal["admin_requested", "outbound", "lifecycle"]
    reference: str


class VerticalStatusV1(_V1Model):
    """Operator-safe command projection: no raw collection input or bridge location."""

    version: Literal["v1"] = "v1"
    command_id: str
    attempt_id: str
    state: str
    blocking_stage: str | None = None
    evidence_references: list[VerticalEvidenceReferenceV1] = Field(default_factory=list)
    recovery_action: str
    side_effect_uncertainty: bool
    updated_at: datetime
