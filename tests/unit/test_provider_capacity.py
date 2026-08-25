from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.schemas.provider import ModelProviderRead
from backend.schemas.provider_capacity import (
    ProviderCapacityRead,
    ProviderCapacityState,
)


def _provider(**overrides):
    values = {
        "id": "provider-1",
        "name": "Local Claude",
        "provider_type": "local",
        "base_url": None,
        "api_key": None,
        "default_model": "local-model",
        "notes": None,
        "enabled": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unavailable_capacity_serializes_without_guessed_quota():
    projection = ProviderCapacityRead.unavailable()

    payload = projection.model_dump(mode="json")

    assert payload["state"] == "unavailable"
    assert payload["usage"] is None
    assert "remaining_percent" not in payload
    assert "remaining" not in payload


def test_model_provider_projection_defaults_to_unavailable():
    read = ModelProviderRead.from_model(_provider())

    assert read.capacity.state is ProviderCapacityState.UNAVAILABLE
    assert read.capacity.usage is None
    assert read.capacity.model_dump(mode="json")["state"] == "unavailable"


def test_measured_capacity_requires_explicit_adapter_data():
    projection = ProviderCapacityRead.measured(
        {"window": "five_hour", "used_units": 12},
        source="documented-provider-usage-v1",
    )

    assert projection.state is ProviderCapacityState.MEASURED
    assert projection.usage == {"window": "five_hour", "used_units": 12}
    assert projection.source == "documented-provider-usage-v1"

    with pytest.raises(ValidationError, match="requires adapter usage data"):
        ProviderCapacityRead(state=ProviderCapacityState.MEASURED)


def test_not_applicable_capacity_has_no_usage_payload():
    projection = ProviderCapacityRead.not_applicable()

    assert projection.model_dump(mode="json") == {
        "state": "not_applicable",
        "usage": None,
        "measured_at": None,
        "source": None,
        "reason": "Runtime has no provider quota semantics",
    }

    with pytest.raises(ValidationError, match="must not include measured usage data"):
        ProviderCapacityRead(
            state=ProviderCapacityState.UNAVAILABLE,
            usage={"remaining": 0},
        )
