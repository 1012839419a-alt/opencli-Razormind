from datetime import datetime
from typing import Any, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, Field

from backend.schemas.common import UTCModel

PAW_MAX_PROMPT_CHARS = 8_192
PAW_MAX_TOKENS = 512
PAW_CONFIG_KEYS = frozenset({"max_tokens", "output_schema"})


def validate_paw_agent_config(
    processor_type: str, prompt_template: str, processor_config: dict[str, Any]
) -> None:
    if processor_type != "paw":
        return
    if not isinstance(prompt_template, str) or not prompt_template.strip():
        raise ValueError("paw.prompt_template_required")
    if len(prompt_template) > PAW_MAX_PROMPT_CHARS:
        raise ValueError("paw.prompt_template_too_large")
    if not isinstance(processor_config, dict) or set(processor_config) - PAW_CONFIG_KEYS:
        raise ValueError("paw.processor_config_invalid")
    max_tokens = processor_config.get("max_tokens")
    if max_tokens is not None and (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or not 1 <= max_tokens <= PAW_MAX_TOKENS
    ):
        raise ValueError("paw.max_tokens_invalid")
    output_schema = processor_config.get("output_schema")
    if output_schema is not None:
        if not isinstance(output_schema, dict):
            raise ValueError("paw.output_schema_invalid")
        try:
            Draft202012Validator.check_schema(output_schema)
        except SchemaError as exc:
            raise ValueError("paw.output_schema_invalid") from exc


class AIAgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    processor_type: str = "claude"
    model: Optional[str] = None
    prompt_template: str = ""
    processor_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    provider_id: Optional[str] = None


class AIAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    processor_type: Optional[str] = None
    model: Optional[str] = None
    prompt_template: Optional[str] = None
    processor_config: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None
    provider_id: Optional[str] = None


class AIAgentRead(UTCModel):
    id: str
    name: str
    description: Optional[str]
    processor_type: str
    model: Optional[str]
    prompt_template: str
    processor_config: dict[str, Any]
    enabled: bool
    provider_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
