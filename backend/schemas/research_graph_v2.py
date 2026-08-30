"""Authorized, non-authoritative ResearchGraph V2 event contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

import backend.schemas.record as record_schema


class _V2Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")




class ResearchGraphV2ActorEvidence(_V2Model):
    actor_type: Literal["user"]
    actor_id: str = Field(min_length=1, max_length=36)
    principal: str = Field(min_length=1, max_length=255)
    capability: Literal["inbox.work", "actions.approve"]
    policy_version: Literal["workspace-rbac-v1"]
    authorized_at: datetime


class AuthorizedResearchGraphEventV2(_V2Model):
    """Immutable V2 overlay stored inside one WorkflowRunEvent payload."""

    version: Literal["v2"] = "v2"
    event_id: str = Field(min_length=1, max_length=255)
    action: Literal["context", "propose", "verify", "reject", "retract", "pin", "supersede"]
    expected_sequence: int = Field(ge=0)
    expected_revision: str = Field(min_length=1, max_length=128)
    research_revision_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=36)
    project_id: str = Field(min_length=1, max_length=36)
    workflow_id: str = Field(min_length=1, max_length=36)
    studio_workflow_version_id: str = Field(min_length=1, max_length=36)
    run_id: str = Field(min_length=1, max_length=36)
    node_id: str = Field(min_length=1, max_length=255)
    claim_id: str | None = Field(default=None, min_length=1, max_length=255)
    claim_content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    manifest_refs: list[record_schema.ResearchGraphV2ManifestRef] = Field(default_factory=list, max_length=200)
    actor: ResearchGraphV2ActorEvidence
    supersedes_event_id: str | None = Field(default=None, min_length=1, max_length=255)
    pinned_sequence: int | None = Field(default=None, ge=1)


class ResearchGraphV2MutationRequest(_V2Model):
    idempotency_key: str = Field(min_length=1, max_length=255)
    action: Literal["context", "propose", "verify", "reject", "retract", "pin", "supersede"]
    expected_sequence: int = Field(ge=0)
    expected_revision: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=255)
    claim_id: str | None = Field(default=None, min_length=1, max_length=255)
    claim_content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    supersedes_event_id: str | None = Field(default=None, min_length=1, max_length=255)
    manifest_refs: list[record_schema.ResearchGraphV2ManifestRef] = Field(default_factory=list, max_length=200)


class ResearchGraphV2ClaimRead(_V2Model):
    claim_id: str
    content_hash: str
    state: Literal["proposed", "verified", "rejected", "retracted", "superseded"]
    proposer_actor_id: str
    manifest_refs: list[record_schema.ResearchGraphV2ManifestRef]


class ResearchGraphV2PinnedFoldRead(_V2Model):
    sequence: int = Field(ge=1)
    research_revision_id: str
    manifest_set_hash: str = Field(min_length=64, max_length=64)
    blocked: bool = False

class ResearchGraphV2PinnedReference(_V2Model):
    sequence: int = Field(ge=1)
    research_revision_id: str = Field(min_length=1, max_length=128)
    manifest_set_hash: str = Field(min_length=64, max_length=64)


class ResearchGraphV2Read(_V2Model):
    version: Literal["v2"] = "v2"
    sequence: int = Field(ge=0)
    research_revision_id: str
    claims: list[ResearchGraphV2ClaimRead] = Field(default_factory=list)
    next_cursor: str | None = None
    pinned_fold: ResearchGraphV2PinnedFoldRead | None = None
    blocker: str | None = None
    recovery_action: Literal["none", "re_review", "reconcile_manifest"] = "none"
