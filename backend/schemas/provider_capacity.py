"""Provider capacity projections with an explicit, honest availability state.

Capacity is intentionally not a quota calculator.  A provider-specific usage
adapter may supply opaque usage data when it has a documented endpoint; when
there is no such adapter the projection remains ``unavailable``.  No elapsed
runtime, request count, or other local observation is used to manufacture a
remaining percentage.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ProviderCapacityState(StrEnum):
    """Availability of provider capacity evidence."""

    MEASURED = "measured"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class ProviderCapacityRead(BaseModel):
    """Serialized provider capacity evidence.

    ``usage`` is deliberately opaque: providers do not share a quota schema,
    so an adapter owns the shape of its documented response.  In particular,
    this model has no derived ``remaining_percent`` field.
    """

    model_config = ConfigDict(extra="forbid")

    state: ProviderCapacityState
    usage: dict[str, JsonValue] | None = None
    measured_at: datetime | None = None
    source: str | None = Field(default=None, min_length=1, max_length=255)
    reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_evidence(self) -> ProviderCapacityRead:
        if self.state is ProviderCapacityState.MEASURED:
            if self.usage is None:
                raise ValueError("measured capacity requires adapter usage data")
            if self.reason is not None:
                raise ValueError("measured capacity cannot include an unavailable reason")
            return self
        if self.usage is not None or self.measured_at is not None:
            raise ValueError("unavailable capacity must not include measured usage data")
        return self

    @classmethod
    def unavailable(
        cls, *, reason: str = "No supported provider usage endpoint"
    ) -> ProviderCapacityRead:
        return cls(state=ProviderCapacityState.UNAVAILABLE, reason=reason)

    @classmethod
    def not_applicable(
        cls, *, reason: str = "Runtime has no provider quota semantics"
    ) -> ProviderCapacityRead:
        return cls(state=ProviderCapacityState.NOT_APPLICABLE, reason=reason)

    @classmethod
    def measured(
        cls,
        usage: Mapping[str, JsonValue],
        *,
        source: str,
        measured_at: datetime | None = None,
    ) -> ProviderCapacityRead:
        """Build a measured projection from an explicit provider adapter result."""
        return cls(
            state=ProviderCapacityState.MEASURED,
            usage=dict(usage),
            measured_at=measured_at,
            source=source,
        )


def project_provider_capacity(provider: Any) -> ProviderCapacityRead:
    """Project only explicit adapter evidence from a provider-like object.

    Existing ``ModelProvider`` rows do not carry usage evidence, so they
    serialize as ``unavailable``.  A future documented adapter can attach a
    ``capacity`` projection (or its serialized mapping) without changing this
    API; no other provider fields are consulted.
    """

    value = getattr(provider, "capacity", None)
    if value is None:
        return ProviderCapacityRead.unavailable()
    if isinstance(value, ProviderCapacityRead):
        return value
    if isinstance(value, Mapping):
        return ProviderCapacityRead.model_validate(value)
    raise TypeError("provider capacity adapter result must be a mapping or ProviderCapacityRead")
