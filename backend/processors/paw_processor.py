"""Governed adapter for the fixed local PAW enrichment sidecar."""
import ipaddress
import json
import logging
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from backend.config import get_settings
from backend.processors.base import AbstractProcessor, ProcessingResult
from backend.processors.registry import register_processor
from backend.security.url_guard import SSRFValidationError, guarded_async_client

if TYPE_CHECKING:
    from backend.models.record import CollectedRecord

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "opencli.paw.runtime.v1"
MAX_INPUT_CHARS = 8_192
MAX_TOKENS = 512
MAX_OUTPUT_BYTES = 65_536
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")
_PROGRAM_ID_RE = re.compile(r"^[a-f0-9]{16,64}$")
_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["contractVersion", "programId", "enrichment"],
    "properties": {
        "contractVersion": {"const": CONTRACT_VERSION},
        "programId": {"type": "string", "minLength": 1},
        "enrichment": {"type": "object"},
    },
}
_SENSITIVE_PLACEHOLDER_TERMS = (
    "cookie",
    "token",
    "secret",
    "password",
    "auth",
    "headers",
    "raw_html",
    "html",
)


def _is_local_paw_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname
    if hostname in {"paw-runtime", "localhost"}:
        return True
    if hostname is None:
        return False
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _has_sensitive_placeholder(template: str) -> bool:
    return any(
        any(term in placeholder.lower() for term in _SENSITIVE_PLACEHOLDER_TERMS)
        for placeholder in _PLACEHOLDER_RE.findall(template)
    )
_RESPONSE_VALIDATOR = Draft202012Validator(_RESPONSE_SCHEMA)


def _merged_config(config: dict[str, Any]) -> dict[str, Any]:
    nested = config.get("config")
    if isinstance(nested, dict):
        return {**nested, **{key: value for key, value in config.items() if key != "config"}}
    return config


def _render(template: str, data: dict[str, Any]) -> str:
    return _PLACEHOLDER_RE.sub(lambda match: str(data.get(match.group(1), "")), template)


def _validate_response(
    data: Any,
    program_id: str,
    output_validator: Draft202012Validator | None,
) -> dict[str, Any]:
    try:
        _RESPONSE_VALIDATOR.validate(data)
    except ValidationError as exc:
        raise ValueError("response.schema_invalid") from exc
    if data["programId"] != program_id:
        raise ValueError("response.program_mismatch")
    enrichment = data["enrichment"]
    if output_validator is not None:
        try:
            output_validator.validate(enrichment)
        except ValidationError as exc:
            raise ValueError("response.output_schema_invalid") from exc
    try:
        encoded = json.dumps(
            enrichment, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("response.enrichment_invalid") from exc
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError("response.too_large")
    return enrichment


async def _read_bounded_json(response: Any) -> Any:
    body = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_OUTPUT_BYTES:
                raise ValueError("response.too_large")
            body.extend(chunk)
    finally:
        await response.aclose()
    try:
        return json.loads(
            body,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("response.invalid_json") from exc


@register_processor
class PawProcessor(AbstractProcessor):
    """Send only rendered short text to the code-owned PAW sidecar."""

    processor_type = "paw"

    async def process(
        self,
        records: list["CollectedRecord"],
        prompt_template: str,
        config: dict[str, Any],
    ) -> ProcessingResult:
        cfg = _merged_config(config)
        settings = get_settings()
        if not _PROGRAM_ID_RE.fullmatch(settings.paw_program_id):
            return ProcessingResult(success=False, error="runtime.program_not_configured")
        if not _is_local_paw_url(settings.paw_runtime_url):
            return ProcessingResult(
                success=False,
                error="runtime.endpoint_rejected: paw.local_only",
            )
        if _has_sensitive_placeholder(prompt_template):
            return ProcessingResult(success=False, error="request.sensitive_placeholder")
        try:
            max_tokens = int(cfg.get("max_tokens", settings.paw_max_tokens))
        except (TypeError, ValueError):
            return ProcessingResult(success=False, error="request.max_tokens_invalid")
        if not 1 <= max_tokens <= min(MAX_TOKENS, settings.paw_max_tokens):
            return ProcessingResult(success=False, error="request.max_tokens_invalid")
        output_schema = cfg.get("output_schema")
        if output_schema is None:
            output_validator = None
        elif not isinstance(output_schema, dict):
            return ProcessingResult(success=False, error="request.output_schema_invalid")
        else:
            try:
                Draft202012Validator.check_schema(output_schema)
                output_validator = Draft202012Validator(output_schema)
            except SchemaError:
                return ProcessingResult(success=False, error="request.output_schema_invalid")

        enrichments: list[dict[str, Any]] = [{} for _ in records]
        failed_indices: set[int] = set()
        inputs: list[str | None] = []
        for index, record in enumerate(records):
            context = getattr(record, "normalized_data", {})
            if not isinstance(context, dict):
                context = {}
            input_text = _render(prompt_template, context)
            if not input_text.strip():
                failed_indices.add(index)
                inputs.append(None)
                logger.warning(
                    "PAW input rejected [%d/%d]: request.input_empty", index + 1, len(records)
                )
                continue
            if len(input_text) > MAX_INPUT_CHARS:
                failed_indices.add(index)
                inputs.append(None)
                logger.warning(
                    "PAW input rejected [%d/%d]: request.input_too_large", index + 1, len(records)
                )
                continue
            inputs.append(input_text)

        if len(failed_indices) == len(records):
            return ProcessingResult(
                success=False,
                enrichments=enrichments,
                error="paw.enrichment_failed",
                failed_indices=failed_indices,
            )

        try:
            client, endpoint = await guarded_async_client(
                settings.paw_runtime_url,
                allow_private=True,
                timeout=settings.paw_runtime_timeout_seconds,
            )
        except SSRFValidationError as exc:
            return ProcessingResult(success=False, error=f"runtime.endpoint_rejected: {exc}")

        async with client as opened_client:
            for index, input_text in enumerate(inputs):
                if input_text is None:
                    continue
                response = None
                try:
                    request = opened_client.build_request(
                        "POST",
                        f"{endpoint.rstrip('/')}/v1/enrich",
                        json={
                            "programId": settings.paw_program_id,
                            "input": input_text,
                            "maxTokens": max_tokens,
                        },
                    )
                    response = await opened_client.send(request, stream=True)
                    response.raise_for_status()
                    enrichments[index] = _validate_response(
                        await _read_bounded_json(response),
                        settings.paw_program_id,
                        output_validator,
                    )
                except Exception as exc:
                    failed_indices.add(index)
                    logger.warning(
                        "PAW enrichment rejected [%d/%d]: %s",
                        index + 1,
                        len(records),
                        exc,
                    )
                finally:
                    if response is not None:
                        await response.aclose()

        return ProcessingResult(
            success=not failed_indices,
            enrichments=enrichments,
            error="paw.enrichment_failed" if failed_indices else None,
            failed_indices=failed_indices,
        )
