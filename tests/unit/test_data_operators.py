"""Unit tests for the deterministic DataFlow operator catalog."""

import pytest

from backend.workflow.data_operators import (
    execute_data_operator,
    get_data_operator,
    get_data_operator_pack,
    list_data_operator_packs,
    list_data_operators,
)


def test_builtin_core_data_pack_owns_the_stable_catalog():
    packs = list_data_operator_packs()

    assert [(pack.id, pack.version) for pack in packs] == [
        ("builtin.core-data", "1.0.0")
    ]
    assert get_data_operator_pack("builtin.core-data") is packs[0]
    assert get_data_operator_pack("missing") is None
    assert packs[0].operators == list_data_operators()


def test_catalog_exposes_all_stable_operator_ids():
    assert [operator.id for operator in list_data_operators()] == [
        "core.evaluate.quality",
        "core.filter.quality",
        "core.generate.instruction-pairs",
        "core.refine.text",
    ]
    assert [operator.kind for operator in list_data_operators()] == [
        "evaluate",
        "filter",
        "generate",
        "refine",
    ]
    assert get_data_operator("core.filter.quality").label == "Filter quality"
    assert get_data_operator("missing") is None


def test_generate_creates_source_grounded_pair_inside_candidate_envelope():
    source = {
        "candidateId": "doc-1",
        "lineage": [{"nodeId": "import"}],
        "normalizedData": {"title": "Release notes", "content": "Version 2 fixes login."},
    }

    result = execute_data_operator(
        "core.generate.instruction-pairs",
        [source],
        {"instructionTemplate": "Explain {title}: {content}"},
    )

    output = result.items[0]
    assert output["candidateId"] == "doc-1"
    assert output["lineage"] == [{"nodeId": "import"}]
    assert output["normalizedData"]["instruction"] == (
        "Explain Release notes: Version 2 fixes login."
    )
    assert output["normalizedData"]["response"] == "Version 2 fixes login."
    assert "instruction" not in output
    assert "instruction" not in source["normalizedData"]


def test_filter_reports_deterministic_rejection_reasons():
    result = execute_data_operator(
        "core.filter.quality",
        [
            {"id": 1, "title": "Good", "content": "acceptable text"},
            {"id": 2, "title": "Short", "content": "short"},
            {"id": 3, "title": "Blocked", "content": "contains forbidden phrase"},
            {"id": 4, "content": "acceptable text", "title": ""},
        ],
        {"requiredFields": ["title"], "minLength": 10, "blocklist": ["forbidden"]},
    )

    assert [item["id"] for item in result.items] == [1]
    assert result.metrics == {
        "inputCount": 4,
        "outputCount": 1,
        "rejectedCount": 3,
        "rejectionReasons": {
            "missing_required:title": 1,
            "below_min_length": 1,
            "blocklist_match": 1,
        },
    }
    assert result.rejected_count == 3
    assert result.rejected_candidate_ids == ("2", "3", "4")


def test_filter_keeps_valid_record_and_preserves_lineage():
    result = execute_data_operator(
        "core.filter.quality",
        [
            {
                "title": "Useful",
                "content": "A sufficiently long source.",
                "lineage": [{"nodeId": "source"}],
            }
        ],
        {"requiredFields": ["title"], "minLength": 10, "blocklist": ["spam"]},
    )

    assert result.items[0]["lineage"] == [{"nodeId": "source"}]
    assert result.metrics["rejectedCount"] == 0


def test_filter_reports_nested_candidate_id_without_changing_lineage():
    source = {
        "candidateId": "candidate-too-short",
        "lineage": [{"nodeId": "collector", "runId": "run-1"}],
        "normalizedData": {"title": "Brief", "content": "short"},
    }

    result = execute_data_operator(
        "core.filter.quality",
        [source],
        {"requiredFields": ["title"], "minLength": 10},
    )

    assert result.items == []
    assert result.rejected_count == 1
    assert result.rejected_candidate_ids == ("candidate-too-short",)
    assert source["lineage"] == [{"nodeId": "collector", "runId": "run-1"}]


def test_evaluate_adds_explainable_bounded_score():
    result = execute_data_operator(
        "core.evaluate.quality",
        [{"title": "Title", "content": "adequate content"}],
        {"minLength": 10, "maxLength": 30},
    )

    row = result.items[0]
    assert row["qualityScore"] == 1.0
    assert all(criterion["passed"] for criterion in row["qualityCriteria"])
    assert row["qualityCriteria"][-1]["observedLength"] == len("adequate content")


def test_refine_normalizes_whitespace_and_optionally_redacts_pii():
    result = execute_data_operator(
        "core.refine.text",
        [{"content": "  Cafe\u0301\n contact a@example.com or +1 (555) 123-4567  ", "lineage": []}],
        {"redactEmail": True, "redactPhone": True},
    )

    assert result.items[0]["content"] == "Café contact [REDACTED_EMAIL] or [REDACTED_PHONE]"
    assert result.items[0]["lineage"] == []


def test_unknown_operator_and_bad_batch_are_rejected():
    with pytest.raises(ValueError, match="Unknown data operator"):
        execute_data_operator("core.unknown", [])
    with pytest.raises(TypeError, match="list of dictionaries"):
        execute_data_operator("core.filter.quality", [{"content": "ok"}, "not-a-row"])
