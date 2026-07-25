from __future__ import annotations

import copy

import pytest

from backend.schemas.workflow import WorkflowParameterInterfaceField
from backend.workflow.data_operators import (
    execute_data_operator,
    list_data_operator_packs,
    list_data_operator_specs,
    resolve_data_operator,
)
from backend.workflow.dataflow_compat import COMPAT_OPERATOR_DEFINITIONS


def _candidate(
    candidate_id: str = "candidate-1",
    *,
    title: str = "Question",
    content: str = "A useful answer.",
    **extra: object,
) -> dict[str, object]:
    return {
        "candidateId": candidate_id,
        "raw": {"title": title, "content": content},
        "normalizedData": {
            "title": title,
            "content": content,
            "url": "https://example.test/source",
            **extra,
        },
        "contentHash": "old-hash",
        "lineage": [{"nodeId": "normalize"}],
    }


def test_pack_manifest_registers_all_deterministic_operators() -> None:
    operator_ids = {spec.operator_id for spec in list_data_operator_specs()}

    assert len(operator_ids) == 12
    assert resolve_data_operator("data.chunk").kind == "generate"
    assert {pack.pack_id for pack in list_data_operator_packs()} == {
        "builtin.core-data",
        "builtin.text-cleaning",
        "builtin.dataset-preparation",
    }


def test_versioned_registry_keeps_legacy_default_and_resolves_compat_exactly() -> None:
    definition = COMPAT_OPERATOR_DEFINITIONS[0]
    operator_id = definition.get("operatorId", definition.get("operator_id"))
    pack_version = definition.get("packVersion", definition.get("pack_version"))

    assert resolve_data_operator("data.chunk").pack_version == "1.0.0"
    assert resolve_data_operator(operator_id, pack_version).pack_version == pack_version
    assert resolve_data_operator(operator_id, "missing-version") is None


def test_execute_reports_the_resolved_pack_version() -> None:
    definition = COMPAT_OPERATOR_DEFINITIONS[0]
    operator_id = definition.get("operatorId", definition.get("operator_id"))
    pack_version = definition.get("packVersion", definition.get("pack_version"))

    result = execute_data_operator(
        operator_id,
        [],
        {"fields": ["content"], "operations": ["removeExtraSpaces"]},
        pack_version=pack_version,
    )

    assert result.pack_version == pack_version
    assert result.to_details()["packVersion"] == pack_version


def test_execute_rejects_unknown_pack_version() -> None:
    with pytest.raises(ValueError, match="packVersion"):
        execute_data_operator("data.chunk", [], pack_version="9.9.9")


def test_instruction_pairs_generates_training_fields_and_rejects_incomplete() -> None:
    result = execute_data_operator(
        "core.generate.instruction-pairs",
        [_candidate(), _candidate("missing", content="")],
    )

    assert result.items[0]["normalizedData"]["instruction"] == "Question"
    assert result.items[0]["normalizedData"]["output"] == "A useful answer."
    assert result.rejected_candidate_ids == ["missing"]
    assert result.metrics["generatedPairCount"] == 1


def test_quality_filter_uses_stable_rejected_ids_and_counts() -> None:
    result = execute_data_operator(
        "core.filter.quality",
        [_candidate("good"), _candidate("short", content="x")],
        {"minChars": 10},
    )

    assert [item["candidateId"] for item in result.items] == ["good"]
    assert result.rejected_candidate_ids == ["short"]
    assert result.metrics["rejectedItemCount"] == 1


def test_quality_evaluate_attaches_score_without_mutating_input() -> None:
    items = [_candidate()]
    original = copy.deepcopy(items)

    result = execute_data_operator("core.evaluate.quality", items)

    assert 0 <= result.items[0]["normalizedData"]["qualityScore"] <= 1
    assert result.items[0]["candidateId"] == "candidate-1"
    assert items == original


def test_text_refine_collapses_whitespace_and_can_lowercase() -> None:
    result = execute_data_operator(
        "core.refine.text",
        [_candidate(title="  HELLO \n world  ")],
        {"fields": ["title"], "lowercase": True},
    )

    assert result.items[0]["normalizedData"]["title"] == "hello world"
    assert result.metrics["changedFieldCount"] == 1


def test_text_clean_runs_configured_operations_in_order() -> None:
    result = execute_data_operator(
        "text.clean",
        [_candidate(content="<p>Hello&nbsp; WORLD!!!</p> https://invalid.test")],
        {
            "fields": ["content"],
            "operations": [
                "htmlEntities",
                "htmlTags",
                "urls",
                "lowercase",
                "repeatedPunctuation",
                "whitespace",
            ],
        },
    )

    assert result.items[0]["normalizedData"]["content"] == "hello world!"
    assert result.items[0]["lineage"] == [{"nodeId": "normalize"}]


def test_text_rule_filter_reports_each_failed_rule() -> None:
    result = execute_data_operator(
        "text.rule-filter",
        [
            _candidate("ok", content="A useful clean sentence."),
            _candidate("blocked", content="buy SPAM now"),
        ],
        {"fields": ["content"], "minWords": 3, "blocklist": ["spam"]},
    )

    assert [item["candidateId"] for item in result.items] == ["ok"]
    assert result.rejected_candidate_ids == ["blocked"]
    assert result.metrics["ruleHits"] == {"blocklist": 1}


@pytest.mark.parametrize("mode", ["exact", "simhash"])
def test_text_deduplicate_keeps_first_and_is_deterministic(mode: str) -> None:
    items = [
        _candidate("first", title="", content="same content"),
        _candidate("second", title="", content="same content"),
    ]

    first = execute_data_operator("text.deduplicate", items, {"mode": mode})
    second = execute_data_operator("text.deduplicate", items, {"mode": mode})

    assert [item["candidateId"] for item in first.items] == ["first"]
    assert first.rejected_candidate_ids == ["second"]
    assert first == second


def test_text_statistics_attaches_exploration_metrics() -> None:
    result = execute_data_operator(
        "text.statistics",
        [_candidate(title="", content="One two two. Three!")],
        {"fields": ["content"]},
    )

    stats = result.items[0]["normalizedData"]["dataflowStatistics"]
    assert stats == {
        "characterCount": 19,
        "wordCount": 4,
        "sentenceCount": 2,
        "uniqueWordRatio": 0.75,
        "symbolRatio": 0.125,
    }


def test_data_project_selects_renames_coalesces_and_casts() -> None:
    result = execute_data_operator(
        "data.project",
        [_candidate(count="4", backup="fallback")],
        {
            "select": ["title", "count"],
            "rename": {"title": "prompt"},
            "coalesce": {"context": ["missing", "backup"]},
            "casts": {"count": "integer"},
        },
    )

    assert result.items[0]["normalizedData"] == {
        "prompt": "Question",
        "count": 4,
        "context": "fallback",
    }


def test_data_chunk_preserves_lineage_and_derives_stable_candidate_ids() -> None:
    item = _candidate(content="abcdefghij")
    config = {"field": "content", "chunkSize": 4, "overlap": 1}

    first = execute_data_operator("data.chunk", [item], config)
    second = execute_data_operator("data.chunk", [item], config)

    assert [chunk["normalizedData"]["content"] for chunk in first.items] == [
        "abcd",
        "defg",
        "ghij",
    ]
    assert [chunk["candidateId"] for chunk in first.items] == [
        chunk["candidateId"] for chunk in second.items
    ]
    assert all(chunk["lineage"] == item["lineage"] for chunk in first.items)
    assert len({chunk["candidateId"] for chunk in first.items}) == 3


@pytest.mark.parametrize(
    ("operator_id", "config", "message"),
    [
        ("core.filter.quality", {"minChars": 3, "maxChars": 2}, "maxChars"),
        ("core.evaluate.quality", {"minLength": 3, "maxLength": 2}, "maxLength"),
        ("text.rule-filter", {"minChars": 3, "maxChars": 2}, "maxChars"),
        ("text.rule-filter", {"minWords": 3, "maxWords": 2}, "maxWords"),
    ],
)
def test_minimum_above_maximum_fails_closed(
    operator_id: str, config: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        execute_data_operator(operator_id, [], config)


@pytest.mark.parametrize("distance", [-1, 65])
def test_simhash_distance_must_fit_64_bit_fingerprint(distance: int) -> None:
    with pytest.raises(ValueError, match="maxHammingDistance"):
        execute_data_operator(
            "text.deduplicate", [], {"mode": "simhash", "maxHammingDistance": distance}
        )


def test_cast_and_template_errors_do_not_include_input_values() -> None:
    with pytest.raises(ValueError) as cast_error:
        execute_data_operator(
            "data.project",
            [_candidate(count="private-value")],
            {"casts": {"count": "integer"}},
        )
    assert "private-value" not in str(cast_error.value)

    with pytest.raises(ValueError) as template_error:
        execute_data_operator(
            "core.generate.instruction-pairs",
            [_candidate(title="private-title")],
            {"instructionTemplate": "{missing}"},
        )
    assert "private-title" not in str(template_error.value)


def test_data_qa_extract_emits_grounded_pairs_with_source_refs() -> None:
    item = _candidate(
        content="Grounding context",
        qaPairs=[
            {"question": "Q1?", "answer": "A1", "citations": ["p1"]},
            {"q": "Q2?", "a": "A2"},
        ],
    )

    result = execute_data_operator("data.qa-extract", [item])

    assert [entry["normalizedData"]["question"] for entry in result.items] == ["Q1?", "Q2?"]
    assert result.items[0]["normalizedData"]["context"] == "Grounding context"
    assert result.items[0]["normalizedData"]["sourceRefs"] == [
        {"nodeId": "normalize"},
        {"url": "https://example.test/source"},
    ]
    assert result.items[0]["normalizedData"]["citations"] == ["p1"]


@pytest.mark.parametrize(
    ("format_name", "expected"),
    [
        (
            "alpaca",
            {"instruction": "Q?", "input": "Context", "output": "A."},
        ),
        (
            "sharegpt",
            [
                {"from": "human", "value": "Q?\n\nContext"},
                {"from": "gpt", "value": "A."},
            ],
        ),
    ],
)
def test_data_training_format_supports_alpaca_and_sharegpt(
    format_name: str, expected: object
) -> None:
    result = execute_data_operator(
        "data.training-format",
        [_candidate(question="Q?", answer="A.", context="Context")],
        {"format": format_name},
    )

    assert result.items[0]["normalizedData"]["trainingData"] == expected


def test_empty_batch_has_consistent_metrics_for_every_operator() -> None:
    for spec in list_data_operator_specs():
        result = execute_data_operator(spec.operator_id, [])
        assert result.items == []
        assert result.rejected_candidate_ids == []
        assert result.metrics["inputItemCount"] == 0
        assert result.metrics["outputItemCount"] == 0


def test_invalid_operator_and_config_fail_closed() -> None:
    with pytest.raises(ValueError, match="Unknown data operator"):
        execute_data_operator("missing", [])
    with pytest.raises(ValueError, match="Unsupported config"):
        execute_data_operator("text.clean", [], {"surprise": True})
    with pytest.raises(ValueError, match="overlap"):
        execute_data_operator("data.chunk", [], {"chunkSize": 4, "overlap": 4})


def test_rejected_count_does_not_fabricate_missing_candidate_ids() -> None:
    result = execute_data_operator(
        "core.filter.quality",
        [{"normalizedData": {"content": ""}}],
        {"minChars": 1},
    )

    assert result.rejected_count == 1
    assert result.metrics["rejectedItemCount"] == 1
    assert result.rejected_candidate_ids == []


def test_result_details_use_runtime_camel_case_contract() -> None:
    result = execute_data_operator("text.statistics", [_candidate()])

    assert result.to_details()["operatorId"] == "text.statistics"
    assert result.to_details()["rejectedCandidateIds"] == []


def test_workflow_contract_accepts_data_operator_json_config_field() -> None:
    field = WorkflowParameterInterfaceField(
        id="operator.config",
        label="Config (JSON)",
        groupId="operator",
        type="json",
        binding={"nodeId": "clean", "source": "params", "fieldId": "config"},
        value={"operations": ["whitespace"]},
    )

    assert field.type == "json"
