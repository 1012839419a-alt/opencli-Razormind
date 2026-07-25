"""Versioned deterministic data-preparation operator registry."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import string
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Literal

from backend.workflow.dataflow_compat import (
    COMPAT_EXECUTORS,
    COMPAT_OPERATOR_DEFINITIONS,
)

DataOperatorKind = Literal["generate", "filter", "evaluate", "refine"]
_Executor = Callable[
    [list[dict[str, Any]], dict[str, Any]],
    tuple[list[dict[str, Any]], dict[str, Any], list[str]],
]


@dataclass(frozen=True)
class DataOperatorSpec:
    id: str
    kind: DataOperatorKind
    pack_id: str
    pack_version: str
    label: str
    description: str
    config_keys: tuple[str, ...] = ()

    @property
    def operator_id(self) -> str:
        return self.id

    def to_manifest(self) -> dict[str, object]:
        return {
            "operatorId": self.id,
            "kind": self.kind,
            "packId": self.pack_id,
            "packVersion": self.pack_version,
            "label": self.label,
            "description": self.description,
            "configKeys": list(self.config_keys),
            "inputPort": "recordCandidate[]",
            "outputPort": "recordCandidate[]",
            "deterministic": True,
        }


@dataclass(frozen=True)
class DataOperatorPack:
    id: str
    version: str
    operators: tuple[DataOperatorSpec, ...]

    @property
    def pack_id(self) -> str:
        return self.id

    def to_manifest(self) -> dict[str, object]:
        return {
            "packId": self.id,
            "version": self.version,
            "operators": [spec.to_manifest() for spec in self.operators],
        }


@dataclass(frozen=True)
class DataOperatorResult:
    operator_id: str
    pack_id: str
    pack_version: str
    items: list[dict[str, Any]]
    metrics: dict[str, Any]
    rejected_count: int
    rejected_candidate_ids: list[str]

    def to_details(self) -> dict[str, object]:
        return {
            "operatorId": self.operator_id,
            "packId": self.pack_id,
            "packVersion": self.pack_version,
            "inputItemCount": self.metrics["inputItemCount"],
            "outputItemCount": self.metrics["outputItemCount"],
            "metrics": dict(self.metrics),
            "rejectedCandidateIds": list(self.rejected_candidate_ids),
        }


_CORE_PACK_ID = "builtin.core-data"
_TEXT_PACK_ID = "builtin.text-cleaning"
_DATASET_PACK_ID = "builtin.dataset-preparation"
_LEGACY_VERSION = "1.0.0"

_LEGACY_SPECS = (
    DataOperatorSpec(
        "core.generate.instruction-pairs",
        "generate",
        _CORE_PACK_ID,
        _LEGACY_VERSION,
        "Instruction pairs",
        "Build instruction/output records from normalized candidates.",
        ("instructionField", "responseField", "instructionTemplate"),
    ),
    DataOperatorSpec(
        "core.filter.quality",
        "filter",
        _CORE_PACK_ID,
        _LEGACY_VERSION,
        "Quality filter",
        "Reject records below deterministic text-quality thresholds.",
        (
            "fields",
            "requiredFields",
            "textField",
            "minChars",
            "maxChars",
            "minLength",
            "maxLength",
            "minQuality",
            "blocklist",
        ),
    ),
    DataOperatorSpec(
        "core.evaluate.quality",
        "evaluate",
        _CORE_PACK_ID,
        _LEGACY_VERSION,
        "Quality evaluation",
        "Attach deterministic quality scores and signals.",
        ("fields", "minLength", "maxLength"),
    ),
    DataOperatorSpec(
        "core.refine.text",
        "refine",
        _CORE_PACK_ID,
        _LEGACY_VERSION,
        "Text refine",
        "Normalize whitespace in selected text fields.",
        ("fields", "lowercase", "unicodeForm", "redactEmail", "redactPhone"),
    ),
    DataOperatorSpec(
        "text.clean",
        "refine",
        _TEXT_PACK_ID,
        _LEGACY_VERSION,
        "Text clean",
        "Apply a configurable sequence of deterministic text cleaners.",
        ("fields", "operations", "replacement"),
    ),
    DataOperatorSpec(
        "text.rule-filter",
        "filter",
        _TEXT_PACK_ID,
        _LEGACY_VERSION,
        "Text rule filter",
        "Filter text by length, vocabulary, symbols, and blocklist rules.",
        (
            "fields",
            "minChars",
            "maxChars",
            "minWords",
            "maxWords",
            "minSentences",
            "maxSymbolRatio",
            "minUniqueWordRatio",
            "blocklist",
        ),
    ),
    DataOperatorSpec(
        "text.deduplicate",
        "filter",
        _TEXT_PACK_ID,
        _LEGACY_VERSION,
        "Text deduplicate",
        "Keep the first exact or near-duplicate record.",
        ("fields", "mode", "maxHammingDistance"),
    ),
    DataOperatorSpec(
        "text.statistics",
        "evaluate",
        _TEXT_PACK_ID,
        _LEGACY_VERSION,
        "Text statistics",
        "Attach character, word, sentence, and lexical-diversity statistics.",
        ("fields", "outputField"),
    ),
    DataOperatorSpec(
        "data.project",
        "refine",
        _DATASET_PACK_ID,
        _LEGACY_VERSION,
        "Data project",
        "Select, rename, coalesce, and cast normalized fields.",
        ("select", "rename", "coalesce", "casts"),
    ),
    DataOperatorSpec(
        "data.chunk",
        "generate",
        _DATASET_PACK_ID,
        _LEGACY_VERSION,
        "Data chunk",
        "Split text into deterministic overlapping character chunks.",
        ("field", "chunkSize", "overlap"),
    ),
    DataOperatorSpec(
        "data.qa-extract",
        "generate",
        _DATASET_PACK_ID,
        _LEGACY_VERSION,
        "QA extract",
        "Expand embedded question-answer pairs into grounded candidates.",
        ("pairsField", "contextField"),
    ),
    DataOperatorSpec(
        "data.training-format",
        "refine",
        _DATASET_PACK_ID,
        _LEGACY_VERSION,
        "Training format",
        "Project question-answer candidates to Alpaca or ShareGPT records.",
        ("format", "instructionField", "inputField", "outputField", "resultField"),
    ),
)


def _compat_spec(definition: dict[str, Any]) -> DataOperatorSpec:
    def read(camel: str, snake: str | None = None) -> Any:
        return definition.get(camel, definition.get(snake or camel))

    kind = read("kind")
    if kind not in {"generate", "filter", "evaluate", "refine"}:
        raise ValueError("Compatibility data operator kind is invalid")
    config_keys = read("configKeys", "config_keys") or ()
    if not isinstance(config_keys, (list, tuple)) or any(
        not isinstance(key, str) or not key for key in config_keys
    ):
        raise ValueError("Compatibility data operator configKeys are invalid")
    values = {
        "id": read("operatorId", "operator_id"),
        "pack_id": read("packId", "pack_id"),
        "pack_version": read("packVersion", "pack_version"),
        "label": read("label"),
        "description": read("description"),
    }
    if any(not isinstance(value, str) or not value for value in values.values()):
        raise ValueError("Compatibility data operator definition is incomplete")
    return DataOperatorSpec(
        values["id"],
        kind,
        values["pack_id"],
        values["pack_version"],
        values["label"],
        values["description"],
        tuple(config_keys),
    )


_SPECS = (*_LEGACY_SPECS, *tuple(_compat_spec(item) for item in COMPAT_OPERATOR_DEFINITIONS))
_SPEC_BY_KEY = {(spec.operator_id, spec.pack_version): spec for spec in _SPECS}
if len(_SPEC_BY_KEY) != len(_SPECS):
    raise ValueError("Duplicate data operator id and packVersion")


def _packs() -> tuple[DataOperatorPack, ...]:
    keys = dict.fromkeys((spec.pack_id, spec.pack_version) for spec in _SPECS)
    return tuple(
        DataOperatorPack(
            pack_id,
            version,
            tuple(
                spec
                for spec in _SPECS
                if spec.pack_id == pack_id and spec.pack_version == version
            ),
        )
        for pack_id, version in keys
    )


_PACKS = _packs()


def resolve_data_operator(
    operator_id: str, pack_version: str | None = None
) -> DataOperatorSpec | None:
    if pack_version is not None:
        return _SPEC_BY_KEY.get((operator_id, pack_version))
    return _SPEC_BY_KEY.get((operator_id, _LEGACY_VERSION))


def list_data_operator_specs() -> tuple[DataOperatorSpec, ...]:
    return _SPECS


def list_data_operator_packs() -> tuple[DataOperatorPack, ...]:
    return _PACKS


def get_data_operator_pack(
    pack_id: str, pack_version: str | None = None
) -> DataOperatorPack | None:
    version = pack_version or _LEGACY_VERSION
    return next(
        (pack for pack in _PACKS if pack.id == pack_id and pack.version == version),
        None,
    )


def execute_data_operator(
    operator_id: str,
    items: list[dict[str, Any]],
    config: dict[str, Any] | None = None,
    *,
    pack_version: str | None = None,
) -> DataOperatorResult:
    spec = resolve_data_operator(operator_id, pack_version)
    if spec is None:
        suffix = f" at packVersion {pack_version}" if pack_version else ""
        raise ValueError(f"Unknown data operator: {operator_id}{suffix}")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Data operator items must be a list of objects")
    resolved_config = dict(config or {})
    unknown = sorted(set(resolved_config) - set(spec.config_keys))
    if unknown:
        raise ValueError(f"Unsupported config for {operator_id}: {', '.join(unknown)}")
    executor = _EXECUTORS.get((operator_id, spec.pack_version))
    if executor is None:
        raise ValueError(
            f"Data operator executor is unavailable: {operator_id} at {spec.pack_version}"
        )
    output, operator_metrics, rejected = executor(
        copy.deepcopy(items), resolved_config
    )
    rejected_count = int(operator_metrics.pop("rejectedInputCount", len(rejected)))
    metrics = {
        "inputItemCount": len(items),
        "outputItemCount": len(output),
        "rejectedItemCount": rejected_count,
        "inputCount": len(items),
        "outputCount": len(output),
        "rejectedCount": rejected_count,
        **operator_metrics,
    }
    return DataOperatorResult(
        operator_id=operator_id,
        pack_id=spec.pack_id,
        pack_version=spec.pack_version,
        items=output,
        metrics=metrics,
        rejected_count=rejected_count,
        rejected_candidate_ids=rejected,
    )


def _instruction_pairs(items, config):
    instruction_field = _string_config(config, "instructionField", "title")
    response_field = _string_config(config, "responseField", "content")
    template = _string_config(config, "instructionTemplate", "{title}")
    output, rejected = [], []
    for index, item in enumerate(items):
        response = _field_text(item, response_field)
        if not response:
            _record_rejection(rejected, item)
            continue
        title = _field_text(item, instruction_field) or "the source content"
        try:
            instruction = template.format(title=title, content=response)
        except (IndexError, KeyError, ValueError) as error:
            raise ValueError(
                "instructionTemplate may only use {title} and {content}"
            ) from error
        normalized = _normalized(item)
        normalized.update(
            {
                "instruction": instruction,
                "input": "",
                "output": response,
                "response": response,
            }
        )
        output.append(_with_normalized(item, normalized, index=index))
    return output, {
        "generatedPairCount": len(output),
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _quality_filter(items, config):
    text_field = _string_config(config, "textField", "content")
    fields = _fields_config(config) if "fields" in config else [text_field]
    minimum = _aliased_length(config, "minChars", "minLength", default=1)
    maximum = _aliased_optional_length(config, "maxChars", "maxLength")
    if maximum is not None and maximum < minimum:
        raise ValueError("maxChars must be greater than or equal to minChars")
    min_quality = _number_config(config, "minQuality", 0.0, 0.0, 1.0)
    required = _string_list(config.get("requiredFields", []), "requiredFields")
    blocklist = [
        term.casefold()
        for term in _string_list(config.get("blocklist", []), "blocklist")
    ]
    output, rejected = [], []
    for item in items:
        text = _combined_text(item, fields)
        score, _ = _quality(text)
        data = _normalized(item)
        reject = any(data.get(field) in (None, "") for field in required)
        reject = reject or any(term in text.casefold() for term in blocklist)
        reject = reject or len(text) < minimum
        reject = reject or (maximum is not None and len(text) > maximum)
        reject = reject or score < min_quality
        if reject:
            _record_rejection(rejected, item)
        else:
            output.append(item)
    return output, {
        "minimumQuality": min_quality,
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _quality_evaluate(items, config):
    fields = _fields_config(config)
    minimum = _int_config(config, "minLength", 20, 0)
    maximum = _optional_int_config(config, "maxLength", 1)
    if maximum is not None and maximum < minimum:
        raise ValueError("maxLength must be greater than or equal to minLength")
    output, scores = [], []
    for index, item in enumerate(items):
        text = _combined_text(item, fields)
        score, signals = _quality(text)
        signals["lengthWithinBounds"] = len(text) >= minimum and (
            maximum is None or len(text) <= maximum
        )
        normalized = _normalized(item)
        normalized.update({"qualityScore": score, "qualitySignals": signals})
        output.append(_with_normalized(item, normalized, index=index))
        scores.append(score)
    average = round(sum(scores) / len(scores), 4) if scores else 0.0
    return output, {"averageQuality": average}, []


def _text_refine(items, config):
    fields = _fields_config(config)
    lowercase = _bool_config(config, "lowercase", False)
    form = _string_config(config, "unicodeForm", "NFKC")
    if form not in {"NFC", "NFD", "NFKC", "NFKD"}:
        raise ValueError("unicodeForm must be one of NFC, NFD, NFKC, or NFKD")
    redact_email = _bool_config(config, "redactEmail", False)
    redact_phone = _bool_config(config, "redactPhone", False)
    output, changed = [], 0
    for index, item in enumerate(items):
        normalized = _normalized(item)
        for field in fields:
            value = normalized.get(field)
            if not isinstance(value, str):
                continue
            refined = _collapse_whitespace(unicodedata.normalize(form, value))
            refined = refined.lower() if lowercase else refined
            if redact_email:
                refined = re.sub(
                    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                    "[REDACTED_EMAIL]",
                    refined,
                )
            if redact_phone:
                refined = re.sub(
                    r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)",
                    "[REDACTED_PHONE]",
                    refined,
                )
            changed += refined != value
            normalized[field] = refined
        output.append(_with_normalized(item, normalized, index=index))
    return output, {"changedFieldCount": changed}, []


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def _clean_text(value, operations, replacement):
    cleaned = value
    for operation in operations:
        if operation == "htmlEntities":
            cleaned = html.unescape(cleaned)
        elif operation == "htmlTags":
            parser = _TextExtractor()
            parser.feed(cleaned)
            parser.close()
            cleaned = " ".join(parser.parts)
        elif operation == "urls":
            cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned)
        elif operation == "lowercase":
            cleaned = cleaned.lower()
        elif operation == "emoji":
            cleaned = "".join(
                c for c in cleaned if not unicodedata.category(c).startswith(("So", "Cs"))
            )
        elif operation == "numbers":
            cleaned = re.sub(r"\d+", " ", cleaned)
        elif operation == "punctuation":
            cleaned = "".join(" " if c in string.punctuation else c for c in cleaned)
        elif operation == "repeatedPunctuation":
            cleaned = re.sub(r"([!?.,;:])\1+", r"\1", cleaned)
        elif operation == "references":
            cleaned = re.sub(r"\[(?:\d+|[^\]]+,\s*\d{4})\]", " ", cleaned)
        elif operation == "imageReferences":
            cleaned = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", cleaned)
        elif operation == "pii":
            cleaned = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", replacement, cleaned)
            cleaned = re.sub(
                r"(?<!\d)(?:\+?\d[\d ()-]{7,}\d)(?!\d)", replacement, cleaned
            )
        elif operation == "whitespace":
            cleaned = _collapse_whitespace(cleaned)
    return cleaned.strip()


def _text_clean(items, config):
    fields = _fields_config(config)
    operations = _string_list(
        config.get("operations", ["htmlEntities", "htmlTags", "urls", "whitespace"]),
        "operations",
    )
    supported = {
        "htmlEntities", "htmlTags", "urls", "lowercase", "emoji", "numbers",
        "punctuation", "repeatedPunctuation", "references", "imageReferences",
        "pii", "whitespace",
    }
    unknown = sorted(set(operations) - supported)
    if unknown:
        raise ValueError(f"Unsupported text.clean operations: {', '.join(unknown)}")
    replacement = _string_config(config, "replacement", "[REDACTED]")
    output, changed = [], 0
    for index, item in enumerate(items):
        normalized = _normalized(item)
        for field in fields:
            value = normalized.get(field)
            if isinstance(value, str):
                cleaned = _clean_text(value, operations, replacement)
                changed += cleaned != value
                normalized[field] = cleaned
        output.append(_with_normalized(item, normalized, index=index))
    return output, {"changedFieldCount": changed, "operations": operations}, []


def _rule_filter(items, config):
    fields = _fields_config(config)
    min_chars = _int_config(config, "minChars", 1, 0)
    max_chars = _optional_int_config(config, "maxChars", 1)
    min_words = _int_config(config, "minWords", 0, 0)
    max_words = _optional_int_config(config, "maxWords", 1)
    min_sentences = _int_config(config, "minSentences", 0, 0)
    max_symbol = _number_config(config, "maxSymbolRatio", 1.0, 0.0, 1.0)
    min_unique = _number_config(config, "minUniqueWordRatio", 0.0, 0.0, 1.0)
    if max_chars is not None and max_chars < min_chars:
        raise ValueError("maxChars must be greater than or equal to minChars")
    if max_words is not None and max_words < min_words:
        raise ValueError("maxWords must be greater than or equal to minWords")
    blocklist = [
        value.casefold()
        for value in _string_list(config.get("blocklist", []), "blocklist")
    ]
    output, rejected, hits = [], [], {}
    for item in items:
        text, failed = _combined_text(item, fields), []
        stats = _statistics(text)
        checks = (
            ("minChars", stats["characterCount"] < min_chars),
            ("maxChars", max_chars is not None and stats["characterCount"] > max_chars),
            ("minWords", stats["wordCount"] < min_words),
            ("maxWords", max_words is not None and stats["wordCount"] > max_words),
            ("minSentences", stats["sentenceCount"] < min_sentences),
            ("maxSymbolRatio", stats["symbolRatio"] > max_symbol),
            ("minUniqueWordRatio", stats["uniqueWordRatio"] < min_unique),
            ("blocklist", any(value in text.casefold() for value in blocklist)),
        )
        failed = [name for name, condition in checks if condition]
        if failed:
            _record_rejection(rejected, item)
            for name in failed:
                hits[name] = hits.get(name, 0) + 1
        else:
            output.append(item)
    return output, {
        "ruleHits": hits,
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _deduplicate(items, config):
    fields = _fields_config(config)
    mode = _string_config(config, "mode", "exact")
    if mode not in {"exact", "simhash"}:
        raise ValueError("text.deduplicate mode must be exact or simhash")
    distance = _int_config(config, "maxHammingDistance", 3, 0)
    if distance > 64:
        raise ValueError("maxHammingDistance must be between 0 and 64")
    output, rejected, exact_seen, fingerprints = [], [], set(), []
    for item in items:
        text = _collapse_whitespace(_combined_text(item, fields)).casefold()
        if mode == "exact":
            duplicate = text in exact_seen
            exact_seen.add(text)
        else:
            fingerprint = _simhash(text)
            duplicate = any(
                (fingerprint ^ previous).bit_count() <= distance
                for previous in fingerprints
            )
            fingerprints.append(fingerprint)
        if duplicate:
            _record_rejection(rejected, item)
        else:
            output.append(item)
    return output, {
        "duplicateCount": len(items) - len(output),
        "mode": mode,
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _text_statistics(items, config):
    fields = _fields_config(config)
    output_field = _string_config(config, "outputField", "dataflowStatistics")
    output, total_words = [], 0
    for index, item in enumerate(items):
        stats = _statistics(_combined_text(item, fields))
        normalized = _normalized(item)
        normalized[output_field] = stats
        output.append(_with_normalized(item, normalized, index=index))
        total_words += stats["wordCount"]
    average = round(total_words / len(items), 4) if items else 0.0
    return output, {"averageWordCount": average}, []


def _project(items, config):
    selected = _string_list(config.get("select", []), "select")
    rename = _string_mapping(config.get("rename", {}), "rename")
    coalesce = _string_list_mapping(config.get("coalesce", {}), "coalesce")
    casts = _string_mapping(config.get("casts", {}), "casts")
    output = []
    for index, item in enumerate(items):
        source = _normalized(item)
        projected = (
            {key: source[key] for key in selected if key in source}
            if selected else source
        )
        for target, candidates in coalesce.items():
            for candidate in candidates:
                if source.get(candidate) not in (None, ""):
                    projected[target] = source[candidate]
                    break
        for old, new in rename.items():
            if old in projected:
                projected[new] = projected.pop(old)
        for field, cast in casts.items():
            if field in projected:
                projected[field] = _cast(projected[field], cast)
        output.append(_with_normalized(item, projected, index=index))
    return output, {
        "projectedFieldCount": sum(len(_normalized(item)) for item in output)
    }, []


def _chunk(items, config):
    field = _string_config(config, "field", "content")
    size = _int_config(config, "chunkSize", 1000, 1)
    overlap = _int_config(config, "overlap", 0, 0)
    if overlap >= size:
        raise ValueError("data.chunk overlap must be smaller than chunkSize")
    output, rejected, step = [], [], size - overlap
    for index, item in enumerate(items):
        text = _field_text(item, field)
        if not text:
            _record_rejection(rejected, item)
            continue
        chunks = []
        for start in range(0, len(text), step):
            chunks.append(text[start : start + size])
            if start + size >= len(text):
                break
        source_id = _candidate_id(item, index)
        for chunk_index, value in enumerate(chunks):
            normalized = _normalized(item)
            normalized.update({
                field: value,
                "chunkIndex": chunk_index,
                "chunkCount": len(chunks),
                "sourceCandidateId": source_id,
            })
            output.append(_with_normalized(
                item, normalized, index=index, derived_key=f"chunk:{chunk_index}"
            ))
    return output, {
        "generatedChunkCount": len(output),
        "rejectedInputCount": sum(not _field_text(item, field) for item in items),
    }, rejected


def _qa_extract(items, config):
    pairs_field = _string_config(config, "pairsField", "qaPairs")
    context_field = _string_config(config, "contextField", "content")
    output, rejected, rejected_count = [], [], 0
    for index, item in enumerate(items):
        pairs = _field_value(item, pairs_field)
        pairs = _field_value(item, f"extra_{pairs_field}") if pairs is None else pairs
        if not isinstance(pairs, list):
            _record_rejection(rejected, item)
            rejected_count += 1
            continue
        generated = 0
        source_id = _candidate_id(item, index)
        context = _field_text(item, context_field)
        for pair_index, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                continue
            question = _first_text(pair, ("question", "q", "instruction"))
            answer = _first_text(pair, ("answer", "a", "output", "response"))
            if not question or not answer:
                continue
            normalized = _normalized(item)
            normalized.update({
                "question": question, "answer": answer, "context": context,
                "sourceCandidateId": source_id, "sourceRefs": _source_refs(item),
                "citations": list(pair.get("citations", []))
                if isinstance(pair.get("citations"), list) else [],
            })
            output.append(_with_normalized(
                item, normalized, index=index, derived_key=f"qa:{pair_index}"
            ))
            generated += 1
        if not generated:
            _record_rejection(rejected, item)
            rejected_count += 1
    return output, {
        "extractedPairCount": len(output),
        "rejectedInputCount": rejected_count,
    }, rejected


def _training_format(items, config):
    format_name = _string_config(config, "format", "alpaca").casefold()
    if format_name not in {"alpaca", "sharegpt"}:
        raise ValueError("data.training-format format must be alpaca or sharegpt")
    instruction_field = _string_config(config, "instructionField", "question")
    input_field = _string_config(config, "inputField", "context")
    output_field = _string_config(config, "outputField", "answer")
    result_field = _string_config(config, "resultField", "trainingData")
    output, rejected = [], []
    for index, item in enumerate(items):
        instruction = _field_text(item, instruction_field)
        response = _field_text(item, output_field)
        if not instruction or not response:
            _record_rejection(rejected, item)
            continue
        input_text = _field_text(item, input_field)
        formatted = (
            {"instruction": instruction, "input": input_text, "output": response}
            if format_name == "alpaca"
            else [
                {"from": "human", "value": f"{instruction}\n\n{input_text}".strip()},
                {"from": "gpt", "value": response},
            ]
        )
        normalized = _normalized(item)
        normalized[result_field] = formatted
        output.append(_with_normalized(item, normalized, index=index))
    return output, {
        "formattedRecordCount": len(output),
        "format": format_name,
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _quality(text):
    stats = _statistics(text)
    nonempty = bool(text.strip())
    length_score = min(stats["characterCount"] / 200, 1.0)
    symbol_score = 1.0 - stats["symbolRatio"]
    score = round(
        (0.1 if nonempty else 0)
        + 0.4 * length_score
        + 0.3 * stats["uniqueWordRatio"]
        + 0.2 * symbol_score,
        4,
    )
    return min(score, 1.0), {
        "nonempty": nonempty,
        "lengthScore": round(length_score, 4),
        "lexicalDiversity": stats["uniqueWordRatio"],
        "symbolScore": round(symbol_score, 4),
    }


def _statistics(text):
    words = re.findall(r"\b[\w'-]+\b", text.casefold(), re.UNICODE)
    non_space = [c for c in text if not c.isspace()]
    symbols = [c for c in non_space if not c.isalnum() and not c.isalpha()]
    sentences = len(re.findall(r"[.!?。！？]+(?:\s|$)", text))
    sentences = 1 if text.strip() and not sentences else sentences
    return {
        "characterCount": len(text),
        "wordCount": len(words),
        "sentenceCount": sentences,
        "uniqueWordRatio": round(len(set(words)) / len(words), 4) if words else 0.0,
        "symbolRatio": round(len(symbols) / len(non_space), 4) if non_space else 0.0,
    }


def _simhash(text):
    tokens = re.findall(r"\w+", text.casefold(), re.UNICODE) or [text]
    vector = [0] * 64
    for token in tokens:
        digest = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
        for bit in range(64):
            vector[bit] += 1 if digest & (1 << bit) else -1
    return sum(1 << bit for bit, weight in enumerate(vector) if weight >= 0)


def _normalized(item):
    value = item.get("normalizedData")
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _with_normalized(item, normalized, *, index, derived_key=None):
    updated = copy.deepcopy(item)
    updated["normalizedData"] = normalized
    updated["contentHash"] = _stable_hash(normalized)
    updated["candidateId"] = (
        _candidate_id(item, index)
        if derived_key is None
        else _derived_candidate_id(item, index, derived_key, normalized)
    )
    return updated


def _candidate_id(item, index):
    value = item.get("candidateId")
    if isinstance(value, str) and value:
        return value
    identity = {
        "contentHash": item.get("contentHash"),
        "normalizedData": item.get("normalizedData"),
        "raw": item.get("raw"),
        "index": index,
    }
    return f"candidate:{_stable_hash(identity)[:24]}"


def _record_rejection(rejected, item):
    value = item.get("candidateId", item.get("id"))
    if isinstance(value, str) and value:
        rejected.append(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        rejected.append(str(value))


def _derived_candidate_id(item, index, key, normalized):
    value = f"{_candidate_id(item, index)}|{key}|{_stable_hash(normalized)}"
    return f"candidate:{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _stable_hash(value):
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _field_value(item, field):
    for value in (item.get("normalizedData"), item.get("raw"), item):
        if isinstance(value, dict) and field in value:
            return value[field]
    return None


def _field_text(item, field):
    value = _field_value(item, field)
    return value.strip() if isinstance(value, str) else ""


def _combined_text(item, fields):
    return "\n".join(value for field in fields if (value := _field_text(item, field)))


def _source_refs(item):
    refs = [copy.deepcopy(value) for value in item.get("lineage", []) if isinstance(value, dict)]
    url = _field_text(item, "url")
    return [*refs, *([{"url": url}] if url else [])]


def _first_text(value, keys):
    return next(
        (
            value[key].strip()
            for key in keys
            if isinstance(value.get(key), str) and value[key].strip()
        ),
        "",
    )


def _collapse_whitespace(value):
    return re.sub(r"\s+", " ", value).strip()


def _fields_config(config):
    return _string_list(config.get("fields", ["title", "content"]), "fields")


def _string_config(config, key, default):
    value = config.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _bool_config(config, key, default):
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _int_config(config, key, default, minimum):
    value = config.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{key} must be an integer >= {minimum}")
    return value


def _optional_int_config(config, key, minimum):
    return None if key not in config or config[key] is None else _int_config(
        config, key, minimum, minimum
    )


def _aliased_length(config, primary, alias, *, default):
    if primary in config and alias in config and config[primary] != config[alias]:
        raise ValueError(f"{primary} and {alias} must match when both are provided")
    return _int_config(config, primary if primary in config else alias, default, 0)


def _aliased_optional_length(config, primary, alias):
    if primary in config and alias in config and config[primary] != config[alias]:
        raise ValueError(f"{primary} and {alias} must match when both are provided")
    return _optional_int_config(config, primary if primary in config else alias, 1)


def _number_config(config, key, default, minimum, maximum):
    value = config.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be a number")
    resolved = float(value)
    if not minimum <= resolved <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return resolved


def _string_list(value, name):
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return list(value)


def _string_mapping(value, name):
    if not isinstance(value, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(item, str)
        or not item
        for key, item in value.items()
    ):
        raise ValueError(f"{name} must map non-empty strings to non-empty strings")
    return dict(value)


def _string_list_mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return {key: _string_list(item, f"{name}.{key}") for key, item in value.items()}


def _cast(value, cast):
    try:
        if cast == "string":
            return str(value)
        if cast == "integer":
            return int(value)
        if cast == "number":
            return float(value)
        if cast == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.casefold() in {"true", "1", "yes"}:
                return True
            if isinstance(value, str) and value.casefold() in {"false", "0", "no"}:
                return False
            raise ValueError
        if cast == "json":
            return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as error:
        raise ValueError(f"Cannot cast value to {cast}") from error
    raise ValueError(f"Unsupported cast: {cast}")


_LEGACY_EXECUTORS: dict[str, _Executor] = {
    "core.generate.instruction-pairs": _instruction_pairs,
    "core.filter.quality": _quality_filter,
    "core.evaluate.quality": _quality_evaluate,
    "core.refine.text": _text_refine,
    "text.clean": _text_clean,
    "text.rule-filter": _rule_filter,
    "text.deduplicate": _deduplicate,
    "text.statistics": _text_statistics,
    "data.project": _project,
    "data.chunk": _chunk,
    "data.qa-extract": _qa_extract,
    "data.training-format": _training_format,
}
_EXECUTORS: dict[tuple[str, str], _Executor] = {
    **{
        (operator_id, _LEGACY_VERSION): executor
        for operator_id, executor in _LEGACY_EXECUTORS.items()
    },
    **COMPAT_EXECUTORS,
}

__all__ = [
    "DataOperatorKind",
    "DataOperatorPack",
    "DataOperatorResult",
    "DataOperatorSpec",
    "execute_data_operator",
    "get_data_operator_pack",
    "list_data_operator_packs",
    "list_data_operator_specs",
    "resolve_data_operator",
]
