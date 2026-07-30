import json
from copy import deepcopy
from datetime import datetime
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from referencing.exceptions import Unresolvable

from backend.models.operations_agent import AgentProfileMode
from backend.schemas.common import UTCModel

AGENT_CONTRACT_CONFIGURATION_KEY = "agent_contract"
AGENT_RUNTIME_BINDING_CONFIGURATION_KEY = "runtime_binding"
MAX_AGENT_SCHEMA_BYTES = 65_536
MAX_AGENT_SCHEMA_DEPTH = 32
MAX_AGENT_MODEL_CONFIGURATION_BYTES = 262_144


class AgentContractV1(BaseModel):
    """Versioned input, output, and state boundary for an Operations Agent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent.contract.v1"]
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]
    state_schema: dict[str, JsonValue]

    @field_validator("input_schema", "output_schema", "state_schema")
    @classmethod
    def schemas_are_valid_json_schema(cls, schema: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if len(json.dumps(schema, allow_nan=False).encode("utf-8")) > MAX_AGENT_SCHEMA_BYTES:
            raise ValueError("JSON Schema exceeds 65536 bytes")
        stack: list[tuple[JsonValue, int]] = [(schema, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_AGENT_SCHEMA_DEPTH:
                raise ValueError("JSON Schema exceeds maximum nesting depth")
            if isinstance(value, dict):
                for keyword in ("$ref", "$dynamicRef"):
                    reference = value.get(keyword)
                    if isinstance(reference, str) and not reference.startswith("#"):
                        raise ValueError("remote JSON Schema references are not supported")
                stack.extend((child, depth + 1) for child in value.values())
            elif isinstance(value, list):
                stack.extend((child, depth + 1) for child in value)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ValueError(f"invalid JSON Schema: {exc.message}") from exc
        return schema


class AgentRuntimeBindingV1(BaseModel):
    """Published binding from one Operations Agent version to an existing edge runtime."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["agent.runtime-binding.v1"]
    agent_url: str = Field(min_length=1, max_length=512)
    runtime: Literal["pi"]
    workflow: str = Field(min_length=1, max_length=255)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    dispatch_timeout_seconds: int = Field(default=600, ge=1, le=3600)

    @field_validator("config")
    @classmethod
    def config_is_task_scoped(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        unsupported = sorted(set(value) - {"timeout_seconds"})
        if unsupported:
            raise ValueError(
                "runtime config is Fleet-owned; unsupported task keys: "
                + ", ".join(unsupported)
            )
        timeout = value.get("timeout_seconds")
        if timeout is not None and (
            not isinstance(timeout, (int, float))
            or isinstance(timeout, bool)
            or not 1 <= timeout <= 3600
        ):
            raise ValueError("config.timeout_seconds must be between 1 and 3600")
        return value

    @field_validator("agent_url")
    @classmethod
    def agent_url_is_http(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("agent_url must be an http/https URL")
        return normalized


def validated_agent_model_configuration(model_configuration: dict[str, Any]) -> dict[str, Any]:
    """Return a detached configuration with canonical versioned agent contracts."""

    configuration = deepcopy(model_configuration)
    if AGENT_CONTRACT_CONFIGURATION_KEY in configuration:
        configuration[AGENT_CONTRACT_CONFIGURATION_KEY] = AgentContractV1.model_validate(
            configuration[AGENT_CONTRACT_CONFIGURATION_KEY]
        ).model_dump(mode="json")
    if AGENT_RUNTIME_BINDING_CONFIGURATION_KEY in configuration:
        configuration[AGENT_RUNTIME_BINDING_CONFIGURATION_KEY] = (
            AgentRuntimeBindingV1.model_validate(
                configuration[AGENT_RUNTIME_BINDING_CONFIGURATION_KEY]
            ).model_dump(mode="json")
        )
    if (
        len(json.dumps(configuration, allow_nan=False).encode("utf-8"))
        > MAX_AGENT_MODEL_CONFIGURATION_BYTES
    ):
        raise ValueError("Operations Agent model_configuration exceeds 262144 bytes")
    return configuration


def agent_contract_from_model_configuration(
    model_configuration: dict[str, Any],
) -> AgentContractV1 | None:
    contract = model_configuration.get(AGENT_CONTRACT_CONFIGURATION_KEY)
    return None if contract is None else AgentContractV1.model_validate(contract)


def agent_runtime_binding_from_model_configuration(
    model_configuration: dict[str, Any],
) -> AgentRuntimeBindingV1 | None:
    binding = model_configuration.get(AGENT_RUNTIME_BINDING_CONFIGURATION_KEY)
    return None if binding is None else AgentRuntimeBindingV1.model_validate(binding)


def validate_agent_contract_payload(
    contract: AgentContractV1,
    schema_field: Literal["input_schema", "output_schema", "state_schema"],
    payload: dict[str, JsonValue],
) -> None:
    try:
        error = next(
            Draft202012Validator(getattr(contract, schema_field)).iter_errors(payload),
            None,
        )
    except Unresolvable as exc:
        raise ValueError(f"{schema_field}: local schema reference cannot be resolved") from exc
    if error is None:
        return
    path = ".".join(str(part) for part in error.absolute_path)
    location = f" at {path}" if path else ""
    raise ValueError(f"{schema_field}{location}: {error.message}")


class OperationsAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    owning_team_id: str


class OperationsAgentPatch(BaseModel):
    disabled: bool


class OperationsAgentDraftUpdate(BaseModel):
    revision: int = Field(ge=1)
    instructions: str = Field(min_length=1, max_length=20000)
    model_configuration: dict[str, JsonValue] = Field(default_factory=dict)
    tool_configuration: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("model_configuration")
    @classmethod
    def validate_agent_contract(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validated_agent_model_configuration(value)


class OperationsAgentDraftRead(UTCModel):
    revision: int
    instructions: str
    model_configuration: dict
    tool_configuration: dict
    updated_by_user_id: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class OperationsAgentPublish(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PublishedOperationsAgentVersionRead(UTCModel):
    version: int
    draft_revision: int
    instructions: str
    model_configuration: dict
    tool_configuration: dict
    published_by_user_id: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OperationsAgentRunCreate(BaseModel):
    target_resource_type: str = Field(min_length=1, max_length=100)
    target_resource_id: str = Field(min_length=1, max_length=255)
    input_payload: dict[str, JsonValue] = Field(default_factory=dict)
    state_payload: dict[str, JsonValue] = Field(default_factory=dict)


class OperationsAgentRunRead(UTCModel):
    id: str
    workspace_id: str
    operations_agent_id: str
    published_version: int
    profile_version: int
    trigger_type: str
    trigger_reference: str | None
    target_resource_type: str
    target_resource_id: str
    input_payload: dict[str, JsonValue]
    state_payload: dict[str, JsonValue]
    output_payload: dict[str, JsonValue] | None
    error_message: str | None
    status: str
    started_by_user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentProfileCreate(BaseModel):
    mode: AgentProfileMode
    tool_scope: list[str] = Field(default_factory=list)
    resource_scope: list[str] = Field(default_factory=list)
    action_scope: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def automatic_profile_is_explicitly_scoped(self):
        scopes = (self.tool_scope, self.resource_scope, self.action_scope)
        if self.mode == AgentProfileMode.LOW_RISK_AUTOMATIC and (
            not all(scopes) or any("*" in value for scope in scopes for value in scope)
        ):
            raise ValueError(
                "Low-Risk Automatic requires explicit tool, resource, and action scopes"
            )
        return self


class AgentProfileRead(UTCModel):
    version: int
    mode: str
    tool_scope: list[str]
    resource_scope: list[str]
    action_scope: list[str]
    assigned_by_user_id: str
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OperationsAgentRead(UTCModel):
    id: str
    workspace_id: str
    owning_team_id: str
    name: str
    description: str | None
    disabled: bool
    current_published_version: int | None
    current_profile: AgentProfileRead
    effective_profile: AgentProfileRead | None
    created_at: datetime
    updated_at: datetime
