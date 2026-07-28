"""Golden compatibility checks against the SHA-pinned DataFlow subset.

The expected values live in a reviewed fixture derived from the upstream source
identified by its commit and file hashes. The local implementation is the
subject under test, never the source of the golden values.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.workflow.data_operators import (
    execute_data_operator,
    list_data_operator_specs,
    resolve_data_operator,
)
from backend.workflow.dataflow_compat import (
    COMPAT_PACK_VERSION,
    DATAFLOW_ALIAS_SOURCE_IDS,
    DATAFLOW_COMPAT_SHA,
    translate_dataflow_alias,
)

_FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "dataflow"
    / "pinned_f62aa134_golden.json"
)
_GOLDEN = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
_PHASE2_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "dataflow"
    / "pinned_f62aa134_phase2_golden.json"
)
_PHASE2 = json.loads(_PHASE2_PATH.read_text(encoding="utf-8"))


def _project_result(result) -> dict:
    return {
        "candidateIds": [item["candidateId"] for item in result.items],
        "normalizedData": [item["normalizedData"] for item in result.items],
        "lineage": [item["lineage"] for item in result.items],
        "rejectedCandidateIds": result.rejected_candidate_ids,
    }


def test_fixture_is_auditable_and_pinned_to_the_supported_upstream_revision():
    upstream = _GOLDEN["upstream"]

    assert upstream["repository"] == "https://github.com/OpenDCAI/DataFlow"
    assert upstream["sourceSha"] == DATAFLOW_COMPAT_SHA
    assert len(upstream["sourceSha"]) == 40
    assert len(upstream["files"]) == 17
    assert all(len(digest) == 64 for digest in upstream["files"].values())
    assert _GOLDEN["compatibilityPack"] == {
        "packId": "builtin.text-cleaning",
        "packVersion": "1.1.0",
        "aliasCount": 34,
        "canonicalOperators": [
            "text.clean",
            "text.rule-filter",
            "text.deduplicate",
        ],
    }


@pytest.mark.parametrize("case", _GOLDEN["aliases"], ids=lambda case: case["alias"])
def test_all_pinned_dataflow_aliases_translate_to_exact_native_invocations(case):
    invocation = translate_dataflow_alias(
        case["sourceId"],
        case["initConfig"],
        case["runConfig"],
    )
    expected = case["expected"]

    assert DATAFLOW_ALIAS_SOURCE_IDS[case["alias"]] == case["sourceId"]
    assert invocation.source_id == case["sourceId"]
    assert invocation.operator_id == expected["operatorId"]
    assert invocation.kind == expected["kind"]
    assert invocation.pack_id == expected["packId"]
    assert invocation.pack_version == expected["packVersion"]
    assert invocation.config == expected["config"]
    assert invocation.to_params() == {
        "operatorId": expected["operatorId"],
        "packId": expected["packId"],
        "packVersion": expected["packVersion"],
        "config": expected["config"],
    }


@pytest.mark.parametrize(
    "case",
    _GOLDEN["goldenCases"],
    ids=lambda case: case["id"],
)
def test_canonical_v1_1_operators_match_pinned_golden_outputs(case):
    result = execute_data_operator(
        case["operatorId"],
        deepcopy(case["items"]),
        deepcopy(case["config"]),
        pack_version=case["packVersion"],
    )

    assert result.pack_version == "1.1.0"
    assert _project_result(result) == case["expected"]
    assert result.metrics["inputItemCount"] == len(case["items"])
    assert result.metrics["outputItemCount"] == len(
        case["expected"]["candidateIds"]
    )
    assert result.metrics["rejectedItemCount"] == len(
        case["expected"]["rejectedCandidateIds"]
    )


@pytest.mark.parametrize(
    "case",
    _GOLDEN["goldenCases"],
    ids=lambda case: case["id"],
)
def test_canonical_v1_1_execution_is_repeatable_and_does_not_mutate_input(case):
    original = deepcopy(case["items"])

    first = execute_data_operator(
        case["operatorId"],
        case["items"],
        case["config"],
        pack_version=case["packVersion"],
    )
    second = execute_data_operator(
        case["operatorId"],
        case["items"],
        case["config"],
        pack_version=case["packVersion"],
    )

    assert first == second
    assert case["items"] == original


def test_legacy_v1_0_text_clean_contract_remains_unchanged():
    items = [
        {
            "candidateId": "legacy-clean",
            "normalizedData": {"content": "<p>Legacy   clean</p>"},
            "lineage": [{"nodeId": "source"}],
        }
    ]

    result = execute_data_operator(
        "text.clean",
        items,
        {
            "fields": ["content"],
            "operations": ["htmlTags", "whitespace"],
        },
        pack_version="1.0.0",
    )

    assert result.pack_version == "1.0.0"
    assert result.items[0]["candidateId"] == "legacy-clean"
    assert result.items[0]["normalizedData"] == {"content": "Legacy clean"}
    assert result.items[0]["lineage"] == [{"nodeId": "source"}]
    assert result.rejected_candidate_ids == []


def test_registry_exposes_the_exact_legacy_and_v1_1_version_seam():
    specs = [
        spec
        for spec in list_data_operator_specs()
        if spec.pack_id != "builtin.research"
    ]

    assert [
        (
            spec.operator_id,
            spec.pack_version,
            spec.pack_id,
            spec.kind,
            spec.config_keys,
        )
        for spec in specs
    ] == [
        (
            "core.generate.instruction-pairs",
            "1.0.0",
            "builtin.core-data",
            "generate",
            ("instructionField", "responseField", "instructionTemplate"),
        ),
        (
            "core.filter.quality",
            "1.0.0",
            "builtin.core-data",
            "filter",
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
        (
            "core.evaluate.quality",
            "1.0.0",
            "builtin.core-data",
            "evaluate",
            ("fields", "minLength", "maxLength"),
        ),
        (
            "core.refine.text",
            "1.0.0",
            "builtin.core-data",
            "refine",
            (
                "fields",
                "lowercase",
                "unicodeForm",
                "redactEmail",
                "redactPhone",
            ),
        ),
        (
            "text.clean",
            "1.0.0",
            "builtin.text-cleaning",
            "refine",
            ("fields", "operations", "replacement"),
        ),
        (
            "text.rule-filter",
            "1.0.0",
            "builtin.text-cleaning",
            "filter",
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
        (
            "text.deduplicate",
            "1.0.0",
            "builtin.text-cleaning",
            "filter",
            ("fields", "mode", "maxHammingDistance"),
        ),
        (
            "text.statistics",
            "1.0.0",
            "builtin.text-cleaning",
            "evaluate",
            ("fields", "outputField"),
        ),
        (
            "data.project",
            "1.0.0",
            "builtin.dataset-preparation",
            "refine",
            ("select", "rename", "coalesce", "casts"),
        ),
        (
            "data.chunk",
            "1.0.0",
            "builtin.dataset-preparation",
            "generate",
            ("field", "chunkSize", "overlap"),
        ),
        (
            "data.qa-extract",
            "1.0.0",
            "builtin.dataset-preparation",
            "generate",
            ("pairsField", "contextField"),
        ),
        (
            "data.training-format",
            "1.0.0",
            "builtin.dataset-preparation",
            "refine",
            (
                "format",
                "instructionField",
                "inputField",
                "outputField",
                "resultField",
            ),
        ),
        (
            "text.clean",
            "1.1.0",
            "builtin.text-cleaning",
            "refine",
            ("fields", "operations", "htmlEntities"),
        ),
        (
            "text.rule-filter",
            "1.1.0",
            "builtin.text-cleaning",
            "filter",
            ("fields", "rules"),
        ),
        (
            "text.deduplicate",
            "1.1.0",
            "builtin.text-cleaning",
            "filter",
            ("fields", "hashFunction", "mode", "nGram", "diffSize", "outputKey"),
        ),
    ]
    assert resolve_data_operator("text.clean").pack_version == "1.0.0"
    assert (
        resolve_data_operator("text.clean", pack_version=COMPAT_PACK_VERSION).pack_version
        == "1.1.0"
    )


@pytest.mark.parametrize(
    ("source_id", "init_config", "run_config"),
    [
        (
            "dataflow@0000000000000000000000000000000000000000::"
            "dataflow.operators.general_text.refine.lowercase_refiner."
            "LowercaseRefiner",
            {},
            {"input_key": "content"},
        ),
        (
            "dataflow@f62aa1349e0ff14cb737a4cbda1945d04fde85bb::"
            "dataflow.operators.general_text.refine.unknown.UnknownRefiner",
            {},
            {"input_key": "content"},
        ),
        (
            DATAFLOW_ALIAS_SOURCE_IDS["Lowercase"],
            {"unexpected": True},
            {"input_key": "content"},
        ),
    ],
)
def test_unsupported_alias_sha_or_config_fails_closed(
    source_id,
    init_config,
    run_config,
):
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        translate_dataflow_alias(source_id, init_config, run_config)


def test_unsupported_operator_version_fails_closed():
    assert resolve_data_operator("text.clean", pack_version="9.9.9") is None
    with pytest.raises(ValueError, match="Unknown data operator"):
        execute_data_operator(
            "text.clean",
            [],
            {},
            pack_version="9.9.9",
        )


def test_phase2_manifest_locks_alias_count_and_new_source_asset_digests():
    assert _GOLDEN["compatibilityPack"]["aliasCount"] == 34
    assert len(_GOLDEN["upstream"]["files"]) == 17
    assert _GOLDEN["upstream"]["files"][
        "dataflow/operators/general_text/filter/blocklist/en.txt"
    ] == "af851ecef1d5f212caba17339b12ac39cc2fef7d78c74876f67237644fcee8bd"
    assert _GOLDEN["upstream"]["files"][
        "dataflow/operators/general_text/filter/blocklist/zh.txt"
    ] == "a1d9aa037c8b039ef3b40148b3364ce2ca62ce4a955b7082a16ad99f6cbd1bc0"
    assert len(DATAFLOW_ALIAS_SOURCE_IDS) == 34
    assert set(DATAFLOW_ALIAS_SOURCE_IDS) == {
        *(case["alias"] for case in _GOLDEN["aliases"]),
        *(case["alias"] for case in _PHASE2["aliases"]),
    }


@pytest.mark.parametrize(
    "case",
    _PHASE2["aliases"],
    ids=lambda case: case["alias"],
)
def test_phase2_aliases_translate_to_exact_pinned_native_invocations(case):
    source_id = (
        f"dataflow@{_PHASE2['sourceSha']}::{case['dotted']}"
    )
    invocation = translate_dataflow_alias(
        source_id,
        case["initConfig"],
        case["runConfig"],
    )

    assert DATAFLOW_ALIAS_SOURCE_IDS[case["alias"]] == source_id
    assert invocation.source_id == source_id
    assert invocation.operator_id == case["operatorId"]
    assert invocation.kind == case["kind"]
    assert invocation.pack_id == _PHASE2["packId"]
    assert invocation.pack_version == _PHASE2["packVersion"]
    assert invocation.config == case["config"]


@pytest.mark.parametrize(
    "case",
    _PHASE2["ruleBoundaryCases"],
    ids=lambda case: case["id"],
)
def test_all_16_phase2_rules_lock_the_upstream_comparison_boundaries(case):
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS[case["alias"]],
        case["initConfig"],
        {"input_key": "content", "output_key": "phase2_boundary_label"},
    )
    contents = [*case["accepted"], *case["rejected"]]
    items = [
        {
            "candidateId": f"{case['id']}-{index}",
            "normalizedData": {"content": content},
            "lineage": [{"nodeId": "phase2-fixture"}],
        }
        for index, content in enumerate(contents)
    ]

    result = execute_data_operator(
        invocation.operator_id,
        items,
        invocation.config,
        pack_version=invocation.pack_version,
    )

    accepted_count = len(case["accepted"])
    assert [item["candidateId"] for item in result.items] == [
        f"{case['id']}-{index}" for index in range(accepted_count)
    ]
    assert result.rejected_candidate_ids == [
        f"{case['id']}-{index}"
        for index in range(accepted_count, len(contents))
    ]


@pytest.mark.parametrize(
    "case",
    _PHASE2["cleanGoldenCases"],
    ids=lambda case: case["id"],
)
def test_phase2_refiners_match_pinned_date_currency_and_image_regex_goldens(case):
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS[case["alias"]],
        {},
        {"input_key": "content"},
    )
    item = {
        "candidateId": case["id"],
        "normalizedData": {"content": case["input"], "preserved": True},
        "lineage": [{"nodeId": "phase2-fixture"}],
    }

    result = execute_data_operator(
        invocation.operator_id,
        [item],
        invocation.config,
        pack_version=invocation.pack_version,
    )

    assert result.items[0]["normalizedData"] == {
        "content": case["expected"],
        "preserved": True,
    }
    assert result.items[0]["candidateId"] == case["id"]
    assert result.items[0]["lineage"] == [{"nodeId": "phase2-fixture"}]


@pytest.mark.parametrize(
    "case",
    _PHASE2["blocklistCases"],
    ids=lambda case: case["id"],
)
def test_phase2_blocklist_uses_pinned_en_zh_assets_and_inclusive_threshold(case):
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS["Blocklist"],
        {
            "language": case["language"],
            "threshold": case["threshold"],
            "use_tokenizer": False,
        },
        {"input_key": "content", "output_key": "blocklist_boundary_label"},
    )
    contents = [*case["accepted"], *case["rejected"]]
    items = [
        {
            "candidateId": f"{case['id']}-{index}",
            "normalizedData": {"content": content},
            "lineage": [{"nodeId": "phase2-fixture"}],
        }
        for index, content in enumerate(contents)
    ]

    result = execute_data_operator(
        invocation.operator_id,
        items,
        invocation.config,
        pack_version=invocation.pack_version,
    )

    accepted_count = len(case["accepted"])
    assert [item["candidateId"] for item in result.items] == [
        f"{case['id']}-{index}" for index in range(accepted_count)
    ]
    assert result.rejected_candidate_ids == [
        f"{case['id']}-{index}"
        for index in range(accepted_count, len(contents))
    ]


@pytest.mark.parametrize(
    "case",
    _PHASE2["ngramHashCases"],
    ids=lambda case: case["id"],
)
def test_phase2_ngram_hash_locks_first_wins_threshold_and_empty_text(case):
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS["NgramHashDeduplicate"],
        {
            "n_gram": case["nGram"],
            "hash_func": "md5",
            "diff_size": case["diffSize"],
        },
        {"input_key": "content", "output_key": "ngram_boundary_label"},
    )
    items = [
        {
            "candidateId": f"{case['id']}-{index}",
            "normalizedData": {"content": content},
            "lineage": [{"nodeId": "phase2-fixture"}],
        }
        for index, content in enumerate(case["contents"])
    ]

    result = execute_data_operator(
        invocation.operator_id,
        items,
        invocation.config,
        pack_version=invocation.pack_version,
    )

    assert [item["candidateId"] for item in result.items] == [
        f"{case['id']}-{index}" for index in case["selectedIndexes"]
    ]
    assert result.rejected_candidate_ids == [
        f"{case['id']}-{index}" for index in case["rejectedIndexes"]
    ]


@pytest.mark.parametrize("alias", ["AlphaWords", "StopWord", "Blocklist"])
def test_phase2_tokenizer_true_fails_closed_without_a_bundled_tokenizer(alias):
    init_config = {"threshold": 0.5, "use_tokenizer": True}
    if alias == "Blocklist":
        init_config = {
            "language": "en",
            "threshold": 1,
            "use_tokenizer": True,
        }
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS[alias],
        init_config,
        {"input_key": "content"},
    )
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        execute_data_operator(
            invocation.operator_id,
            [
                {
                    "candidateId": f"{alias}-tokenizer",
                    "normalizedData": {"content": "plain input"},
                }
            ],
            invocation.config,
            pack_version=invocation.pack_version,
        )
