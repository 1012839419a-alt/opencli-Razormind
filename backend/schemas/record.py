import json
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.common import UTCModel


class CollectedRecordRead(UTCModel):
    id: str
    task_id: str
    source_id: str
    workflow_id: str | None
    workflow_run_id: str | None
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    ai_enrichment: dict[str, Any] | None
    content_hash: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecordFilter(BaseModel):
    source_id: str | None = None
    task_id: str | None = None
    status: str | None = None
    page: int = 1
    limit: int = 20


class DeliveryAuthorizingActor(Protocol):
    """Approval evidence required by the delivery authorization boundary."""

    actor_type: str
    actor_id: str
    principal: str
    capability: str
    policy_version: str


class _EvidenceManifestModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class ResearchGraphV2ItemKey(_EvidenceManifestModel):
    source_id: str = Field(alias="sourceId", min_length=1, max_length=36)
    event_id: str = Field(alias="eventId", min_length=1, max_length=512)


class ResearchGraphV2RecordRef(ResearchGraphV2ItemKey):
    odp_record_id: int = Field(alias="odpRecordId", ge=1)


class ResearchGraphV2ManifestRef(_EvidenceManifestModel):
    batch_id: str = Field(alias="batchId", min_length=1, max_length=36)
    derivation: Literal["dispatch-task-v1"]
    reconciliation_revision: int = Field(alias="reconciliationRevision", ge=1)
    manifest_schema_version: Literal["v1"] = Field(alias="manifestSchemaVersion")
    manifest_hash: str = Field(alias="manifestHash", min_length=64, max_length=64)
    expected_record_key_set_hash: str = Field(alias="expectedRecordKeySetHash", min_length=64, max_length=64)
    record_ref_set_hash: str = Field(alias="recordRefSetHash", min_length=64, max_length=64)
    materialization_status: Literal["completed", "completed_empty", "partial"] = Field(
        alias="materializationStatus"
    )
    record_refs: list[ResearchGraphV2RecordRef] = Field(
        alias="recordRefs", default_factory=list, max_length=1000
    )
    excluded_item_keys: list[ResearchGraphV2ItemKey] = Field(
        alias="excludedItemKeys", default_factory=list, max_length=1000
    )


def record_ref_set_hash(values: list[dict]) -> str:
    """Hash the canonical, order-independent manifest record-reference set."""
    return sha256(
        json.dumps(
            sorted(
                (
                    str(item.get("source_id", item.get("sourceId", ""))),
                    str(item.get("event_id", item.get("eventId", ""))),
                    int(item.get("odp_record_id", item.get("odpRecordId", 0))),
                )
                for item in values
            ),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
