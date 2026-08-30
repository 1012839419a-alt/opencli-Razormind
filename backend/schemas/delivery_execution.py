"""Redacted Studio and controlled-receiver v2 delivery contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class DeliveryExecutionCreateV1(_Model):
    decision_id: str = Field(min_length=1, max_length=36)


class DeliveryExecutionReadV1(_Model):
    execution_id: str
    decision_id: str
    operation_id: str
    decision_hash: str
    payload_hash: str
    state: str
    outcome: Literal["accepted", "rejected", "unknown"] | None = None
    attempt_count: int
    created_at: datetime
    updated_at: datetime


class DeliveryExecutionListV1(_Model):
    items: list[DeliveryExecutionReadV1]
    next_cursor: str | None = None


Hash64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class DeliveryClaimManifestClaimV1(_Model):
    claim_id: str = Field(min_length=1, max_length=255)
    content_hash: Hash64


class DeliveryClaimManifestV1(_Model):
    schema_version: Literal["delivery-claim-manifest-v1"]
    claims: list[DeliveryClaimManifestClaimV1] = Field(min_length=1, max_length=200)
    manifest_hashes: list[Hash64] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def distinct_claims_and_manifests(self) -> "DeliveryClaimManifestV1":
        if len({claim.claim_id for claim in self.claims}) != len(self.claims):
            raise ValueError("Controlled receiver claims must be distinct")
        if len(set(self.manifest_hashes)) != len(self.manifest_hashes):
            raise ValueError("Controlled receiver manifests must be distinct")
        return self


class ControlledReceiverDeliveryV2(_Model):
    version: Literal["v2"] = "v2"
    receiver_identity: str = Field(min_length=1, max_length=255)
    operation_id: str = Field(min_length=1, max_length=255)
    decision_hash: Hash64
    payload_hash: Hash64
    payload: DeliveryClaimManifestV1


class ControlledReceiverReceiptV2(_Model):
    version: Literal["v2"]
    receiver_identity: str
    operation_id: str
    decision_hash: str
    payload_hash: str
    durable_status: Literal["accepted", "rejected"]
    receipt_id: str
    timestamp: str
    key_id: str
    signature: str
