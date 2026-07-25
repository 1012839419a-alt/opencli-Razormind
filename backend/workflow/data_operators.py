"""Deterministic, dependency-free DataFlow operators for record batches."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DataOperatorSpec:
    """Public description of one batch-to-batch DataFlow operator."""

    id: str
    kind: str
    label: str
    description: str
    config_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataOperatorResult:
    """Output batch plus deterministic execution facts."""

    operator_id: str
    items: list[dict[str, Any]]
    metrics: dict[str, Any]
    rejected_count: int = 0
    rejected_candidate_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DataOperatorPack:
    """Versioned operator bundle exposed to workflow capability projection."""

    id: str
    version: str
    operators: tuple[DataOperatorSpec, ...]


_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{6,}\d)(?!\w)")

_BUILTIN_CORE_DATA_SPECS = (
    DataOperatorSpec(
        id="core.evaluate.quality",
        kind="evaluate",
        label="Evaluate quality",
        description="Attach explainable, deterministic quality criteria and a 0..1 score.",
        config_keys=("minLength", "maxLength"),
    ),
    DataOperatorSpec(
        id="core.filter.quality",
        kind="filter",
        label="Filter quality",
        description="Keep rows meeting required-field, length, and blocklist rules.",
        config_keys=("requiredFields", "minLength", "maxLength", "blocklist", "textField"),
    ),
    DataOperatorSpec(
        id="core.generate.instruction-pairs",
        kind="generate",
        label="Generate instruction pairs",
        description="Derive instruction/response pairs from existing titles and content.",
        config_keys=("instructionTemplate",),
    ),
    DataOperatorSpec(
        id="core.refine.text",
        kind="refine",
        label="Refine text",
        description="Normalize Unicode and whitespace, with optional PII redaction.",
        config_keys=("fields", "unicodeForm", "redactEmail", "redactPhone"),
    ),
)


def list_data_operators() -> tuple[DataOperatorSpec, ...]:
    """List the stable operator catalog in deterministic ID order."""

    return _SPECS


def get_data_operator(operator_id: str) -> DataOperatorSpec | None:
    """Return an operator specification, or ``None`` for an unknown ID."""

    return _SPEC_BY_ID.get(operator_id)


def list_data_operator_specs() -> tuple[DataOperatorSpec, ...]:
    """Compatibility name for consumers that call catalog entries specs."""

    return list_data_operators()


def get_data_operator_spec(operator_id: str) -> DataOperatorSpec | None:
    """Compatibility name for :func:`get_data_operator`."""

    return get_data_operator(operator_id)


def list_data_operator_packs() -> tuple[DataOperatorPack, ...]:
    """List built-in operator packs in deterministic registration order."""

    return _PACKS


def get_data_operator_pack(pack_id: str) -> DataOperatorPack | None:
    """Return a registered operator pack, or ``None`` for an unknown ID."""

    return _PACK_BY_ID.get(pack_id)


def execute_data_operator(
    operator_id: str,
    items: list[dict[str, Any]],
    params: Mapping[str, Any] | None = None,
) -> DataOperatorResult:
    """Run one registered operator without mutating its input batch."""

    if operator_id not in _SPEC_BY_ID:
        raise ValueError(f"Unknown data operator: {operator_id}")
    _validate_items(items)
    config = dict(params or {})
    return _EXECUTORS[operator_id](items, config)


def list_operators() -> tuple[DataOperatorSpec, ...]:
    """Short alias for :func:`list_data_operators`."""

    return list_data_operators()


def get_operator(operator_id: str) -> DataOperatorSpec | None:
    """Short alias for :func:`get_data_operator`."""

    return get_data_operator(operator_id)


def execute_operator(
    operator_id: str,
    items: list[dict[str, Any]],
    params: Mapping[str, Any] | None = None,
) -> DataOperatorResult:
    """Short alias for :func:`execute_data_operator`."""

    return execute_data_operator(operator_id, items, params)


def _generate_instruction_pairs(
    items: list[dict[str, Any]], config: dict[str, Any]
) -> DataOperatorResult:
    template = config.get(
        "instructionTemplate",
        "Use the source material to answer this request: {title}",
    )
    if not isinstance(template, str) or not template.strip():
        raise ValueError("instructionTemplate must be a non-empty string")

    output: list[dict[str, Any]] = []
    skipped = 0
    for item in items:
        data = _item_data(item)
        content = _string(data.get("content")) or _string(data.get("text"))
        if not content:
            skipped += 1
            continue
        title = _string(data.get("title")) or "the source content"
        try:
            instruction = template.format(title=title, content=content)
        except (IndexError, KeyError, ValueError) as error:
            raise ValueError("instructionTemplate may only use {title} and {content}") from error
        row, output_data = _copy_item_data(item)
        output_data["instruction"] = instruction
        output_data["response"] = content
        output.append(row)
    return DataOperatorResult(
        operator_id="core.generate.instruction-pairs",
        items=output,
        metrics={"inputCount": len(items), "outputCount": len(output), "skippedCount": skipped},
    )


def _filter_quality(items: list[dict[str, Any]], config: dict[str, Any]) -> DataOperatorResult:
    required = _string_sequence(config.get("requiredFields", ()), "requiredFields")
    blocklist = tuple(
        term.casefold()
        for term in _string_sequence(config.get("blocklist", ()), "blocklist")
    )
    min_length = _length(config.get("minLength"), "minLength", default=0)
    max_length = _length(config.get("maxLength"), "maxLength", default=None)
    if max_length is not None and max_length < min_length:
        raise ValueError("maxLength must be greater than or equal to minLength")
    text_field = config.get("textField", "content")
    if not isinstance(text_field, str) or not text_field:
        raise ValueError("textField must be a non-empty string")

    output: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    rejected_ids: list[str] = []
    for item in items:
        data = _item_data(item)
        reason = _quality_rejection_reason(
            data, required, min_length, max_length, blocklist, text_field
        )
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
            candidate_id = _candidate_id(item)
            if candidate_id is not None:
                rejected_ids.append(candidate_id)
        else:
            output.append(_copy_item_data(item)[0])
    return DataOperatorResult(
        operator_id="core.filter.quality",
        items=output,
        metrics={
            "inputCount": len(items),
            "outputCount": len(output),
            "rejectedCount": len(items) - len(output),
            "rejectionReasons": reasons,
        },
        rejected_count=len(items) - len(output),
        rejected_candidate_ids=tuple(rejected_ids),
    )


def _evaluate_quality(items: list[dict[str, Any]], config: dict[str, Any]) -> DataOperatorResult:
    min_length = _length(config.get("minLength"), "minLength", default=20)
    max_length = _length(config.get("maxLength"), "maxLength", default=None)
    if max_length is not None and max_length < min_length:
        raise ValueError("maxLength must be greater than or equal to minLength")

    output: list[dict[str, Any]] = []
    for item in items:
        data = _item_data(item)
        title = _string(data.get("title"))
        content = _string(data.get("content")) or _string(data.get("text"))
        content_length = len(content or "")
        length_ok = content_length >= min_length and (
            max_length is None or content_length <= max_length
        )
        criteria = [
            {"name": "titlePresent", "passed": bool(title), "weight": 1 / 3},
            {"name": "contentPresent", "passed": bool(content), "weight": 1 / 3},
            {
                "name": "lengthWithinBounds",
                "passed": length_ok,
                "weight": 1 / 3,
                "observedLength": content_length,
                "minLength": min_length,
                "maxLength": max_length,
            },
        ]
        row, output_data = _copy_item_data(item)
        output_data["qualityCriteria"] = criteria
        output_data["qualityScore"] = round(
            sum(entry["weight"] for entry in criteria if entry["passed"]), 3
        )
        output.append(row)
    return DataOperatorResult(
        operator_id="core.evaluate.quality",
        items=output,
        metrics={"inputCount": len(items), "outputCount": len(output)},
    )


def _refine_text(items: list[dict[str, Any]], config: dict[str, Any]) -> DataOperatorResult:
    fields = _string_sequence(
        config.get("fields", ("title", "content", "text", "instruction", "response")), "fields"
    )
    unicode_form = config.get("unicodeForm", "NFKC")
    if unicode_form not in {"NFC", "NFD", "NFKC", "NFKD"}:
        raise ValueError("unicodeForm must be one of NFC, NFD, NFKC, or NFKD")
    redact_email = config.get("redactEmail", False) is True
    redact_phone = config.get("redactPhone", False) is True

    output: list[dict[str, Any]] = []
    for item in items:
        row, output_data = _copy_item_data(item)
        for field in fields:
            value = output_data.get(field)
            if isinstance(value, str):
                output_data[field] = _refined(value, unicode_form, redact_email, redact_phone)
        output.append(row)
    return DataOperatorResult(
        operator_id="core.refine.text",
        items=output,
        metrics={"inputCount": len(items), "outputCount": len(output)},
    )


_BUILTIN_CORE_DATA_EXECUTORS: dict[
    str, Callable[[list[dict[str, Any]], dict[str, Any]], DataOperatorResult]
] = {
    "core.generate.instruction-pairs": _generate_instruction_pairs,
    "core.filter.quality": _filter_quality,
    "core.evaluate.quality": _evaluate_quality,
    "core.refine.text": _refine_text,
}


@dataclass(frozen=True, slots=True)
class _DataOperatorPackRegistration:
    pack: DataOperatorPack
    executors: Mapping[
        str, Callable[[list[dict[str, Any]], dict[str, Any]], DataOperatorResult]
    ]


_PACK_REGISTRATIONS = (
    _DataOperatorPackRegistration(
        pack=DataOperatorPack(
            id="builtin.core-data",
            version="1.0.0",
            operators=_BUILTIN_CORE_DATA_SPECS,
        ),
        executors=_BUILTIN_CORE_DATA_EXECUTORS,
    ),
)
_PACKS = tuple(registration.pack for registration in _PACK_REGISTRATIONS)
_PACK_BY_ID = {pack.id: pack for pack in _PACKS}
_SPECS = tuple(spec for pack in _PACKS for spec in pack.operators)
_SPEC_BY_ID = {spec.id: spec for spec in _SPECS}
_EXECUTORS = {
    operator_id: executor
    for registration in _PACK_REGISTRATIONS
    for operator_id, executor in registration.executors.items()
}

for registration in _PACK_REGISTRATIONS:
    if {spec.id for spec in registration.pack.operators} != set(
        registration.executors
    ):
        raise RuntimeError(
            f"Pack {registration.pack.id} must bind exactly its declared operators"
        )
if len(_PACK_BY_ID) != len(_PACKS):
    raise RuntimeError("Data operator pack IDs must be unique")
if len(_SPEC_BY_ID) != len(_SPECS) or len(_EXECUTORS) != len(_SPECS):
    raise RuntimeError("Data operator IDs must be unique across packs")


def _validate_items(items: list[dict[str, Any]]) -> None:
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise TypeError("items must be a list of dictionaries")


def _item_data(item: dict[str, Any]) -> dict[str, Any]:
    normalized = item.get("normalizedData")
    return normalized if isinstance(normalized, dict) else item


def _copy_item_data(item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy the envelope and payload without changing host-owned lineage."""

    row = dict(item)
    normalized = item.get("normalizedData")
    if isinstance(normalized, dict):
        row["normalizedData"] = dict(normalized)
        return row, row["normalizedData"]
    return row, row


def _candidate_id(item: dict[str, Any]) -> str | None:
    """Return a declared candidate ID without manufacturing one for flat rows."""

    value = item.get("candidateId")
    if value is None:
        value = item.get("id")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        return value if value else None
    if isinstance(value, int | float):
        return str(value)
    return None


def _quality_rejection_reason(
    item: dict[str, Any],
    required: tuple[str, ...],
    min_length: int,
    max_length: int | None,
    blocklist: tuple[str, ...],
    text_field: str,
) -> str | None:
    missing = [field for field in required if not _present(item.get(field))]
    if missing:
        return f"missing_required:{missing[0]}"
    text = _string(item.get(text_field)) or ""
    if len(text) < min_length:
        return "below_min_length"
    if max_length is not None and len(text) > max_length:
        return "above_max_length"
    haystack = " ".join(value for value in item.values() if isinstance(value, str)).casefold()
    if any(term in haystack for term in blocklist):
        return "blocklist_match"
    return None


def _refined(value: str, unicode_form: str, redact_email: bool, redact_phone: bool) -> str:
    text = re.sub(r"\s+", " ", unicodedata.normalize(unicode_form, value)).strip()
    if redact_email:
        text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    if redact_phone:
        text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _string_sequence(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of non-empty strings")
    if any(not isinstance(entry, str) or not entry for entry in value):
        raise ValueError(f"{name} must be a sequence of non-empty strings")
    return tuple(value)


def _length(value: Any, name: str, default: int | None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


__all__ = [
    "DataOperatorPack",
    "DataOperatorResult",
    "DataOperatorSpec",
    "execute_data_operator",
    "execute_operator",
    "get_data_operator",
    "get_data_operator_pack",
    "get_data_operator_spec",
    "get_operator",
    "list_data_operator_packs",
    "list_data_operators",
    "list_data_operator_specs",
    "list_operators",
]
