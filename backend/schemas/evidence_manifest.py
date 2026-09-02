"""Canonical, redacted evidence-manifest contracts shared across domains."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class EvidenceManifestModel(BaseModel):
    """Strict camel-case base for contracts that carry evidence-manifest references."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ResearchGraphV2ItemKey(EvidenceManifestModel):
    source_id: str = Field(min_length=1, max_length=36)
    event_id: str = Field(min_length=1, max_length=512)


class ResearchGraphV2RecordRef(ResearchGraphV2ItemKey):
    odp_record_id: int = Field(ge=1)


class ResearchGraphV2ManifestRef(EvidenceManifestModel):
    batch_id: str = Field(min_length=1, max_length=36)
    derivation: Literal["dispatch-task-v1"]
    reconciliation_revision: int = Field(ge=1)
    manifest_schema_version: Literal["v1"]
    manifest_hash: str = Field(min_length=64, max_length=64)
    expected_record_key_set_hash: str = Field(min_length=64, max_length=64)
    record_ref_set_hash: str = Field(min_length=64, max_length=64)
    materialization_status: Literal["completed", "completed_empty", "partial"]
    record_refs: list[ResearchGraphV2RecordRef] = Field(default_factory=list, max_length=1000)
    excluded_item_keys: list[ResearchGraphV2ItemKey] = Field(default_factory=list, max_length=1000)


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
