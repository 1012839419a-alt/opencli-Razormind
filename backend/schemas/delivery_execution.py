"""Redacted Studio and controlled-receiver v2 delivery contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
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


class ControlledReceiverDeliveryV2(_Model):
    version: Literal["v2"] = "v2"
    receiver_identity: str = Field(min_length=1, max_length=255)
    operation_id: str = Field(min_length=1, max_length=255)
    decision_hash: str = Field(min_length=64, max_length=64)
    payload_hash: str = Field(min_length=64, max_length=64)
    payload: dict


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
