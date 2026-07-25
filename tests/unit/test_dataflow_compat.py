from __future__ import annotations

import copy

import pytest

from backend.workflow.dataflow_compat import (
    COMPAT_EXECUTORS,
    COMPAT_OPERATOR_DEFINITIONS,
    COMPAT_PACK_VERSION,
    DATAFLOW_ALIAS_SOURCE_IDS,
    DataFlowInvocation,
    translate_dataflow_alias,
)


def _candidate(candidate_id: str, **normalized: object) -> dict[str, object]:
    return {
        "candidateId": candidate_id,
        "normalizedData": normalized,
        "lineage": [{"nodeId": "source"}],
    }


def _invoke(
    alias: str,
    items: list[dict[str, object]],
    init: dict[str, object] | None = None,
    run: dict[str, object] | None = None,
):
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS[alias],
        init,
        {"input_key": "text", **(run or {})},
    )
    executor = COMPAT_EXECUTORS[(invocation.operator_id, invocation.pack_version)]
    return executor(items, invocation.config)


def test_manifest_and_alias_allowlist_are_fixed() -> None:
    assert len(COMPAT_OPERATOR_DEFINITIONS) == 3
    assert len(DATAFLOW_ALIAS_SOURCE_IDS) == 34
    assert {
        (definition["operatorId"], definition["kind"])
        for definition in COMPAT_OPERATOR_DEFINITIONS
    } == {
        ("text.clean", "refine"),
        ("text.rule-filter", "filter"),
        ("text.deduplicate", "filter"),
    }
    assert {
        definition["packVersion"] for definition in COMPAT_OPERATOR_DEFINITIONS
    } == {"1.1.0"}


def test_translation_is_sha_locked_and_returns_detached_invocation() -> None:
    run = {"input_key": "text"}
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS["Lowercase"], {}, run
    )
    run["input_key"] = "changed"

    assert isinstance(invocation, DataFlowInvocation)
    assert invocation.operator_id == "text.clean"
    assert invocation.config == {"fields": ["text"], "operations": ["lowercase"]}
    assert invocation.to_params()["packVersion"] == "1.1.0"
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        translate_dataflow_alias(
            DATAFLOW_ALIAS_SOURCE_IDS["Lowercase"].replace("f62aa134", "00000000"),
            {},
            {"input_key": "text"},
        )


@pytest.mark.parametrize(
    ("alias", "text", "expected", "init"),
    [
        ("RemoveExtraSpaces", "  A\n\t B  ", "A B", None),
        ("Lowercase", "ÄBC", "äbc", None),
        ("HtmlUrlRemover", "<b>A</b> https://x.test/z\nB", "A B", None),
        ("HtmlEntity", "A&nbsp;B＆amp；C&copy;", "ABC&copy;", None),
        ("HtmlEntity", "A&copy;B&nbsp;", "AB&nbsp;", {"html_entities": ["copy"]}),
        ("RemoveEmoji", "A😀✂B", "AB", None),
        ("RemoveNumber", "A1²二B", "A二B", None),
        ("RemovePunctuation", "a,b。c_", "ab。c", None),
        ("RemoveRepetitionsPunctuation", "a!!!__？？b", "a!_？b", None),
    ],
)
def test_refiners_match_pinned_observable_text_semantics(
    alias: str, text: str, expected: str, init: dict[str, object] | None
) -> None:
    items = [_candidate("a", text=text)]
    original = copy.deepcopy(items)

    output, metrics, rejected = _invoke(alias, items, init)

    assert output[0]["normalizedData"]["text"] == expected
    assert output[0]["lineage"] == [{"nodeId": "source"}]
    assert rejected == []
    assert metrics["changedFieldCount"] == 1
    assert items == original


def test_content_null_rejects_blank_and_reports_only_stable_ids() -> None:
    output, metrics, rejected = _invoke(
        "ContentNull",
        [_candidate("ok", text="x"), _candidate("blank", text=" \t"), {"normalizedData": {}}],
    )

    assert [item["candidateId"] for item in output] == ["ok"]
    assert output[0]["normalizedData"]["content_null_filter_label"] == 1
    assert rejected == ["blank"]
    assert metrics["rejectedInputCount"] == 2


def test_word_max_is_exclusive_but_sentence_max_is_inclusive() -> None:
    word_output, _, word_rejected = _invoke(
        "WordNumber",
        [_candidate("two", text="a b"), _candidate("three", text="a b c")],
        {"min_words": 2, "max_words": 3},
    )
    sentence_output, _, sentence_rejected = _invoke(
        "SentenceNumber",
        [_candidate("two", text="A. B."), _candidate("three", text="A. B. C.")],
        {"min_sentences": 2, "max_sentences": 2},
    )

    assert [item["candidateId"] for item in word_output] == ["two"]
    assert word_output[0]["normalizedData"]["word_number_filter_label"] == 2
    assert word_rejected == ["three"]
    assert [item["candidateId"] for item in sentence_output] == ["two"]
    assert sentence_rejected == ["three"]


def test_char_and_unique_word_thresholds_preserve_upstream_comparisons() -> None:
    char_output, _, _ = _invoke(
        "CharNumber",
        [_candidate("pass", text=" a \n b\t"), _candidate("fail", text="a")],
        {"threshold": 2},
    )
    unique_output, _, unique_rejected = _invoke(
        "UniqueWords",
        [_candidate("equal", text="a a"), _candidate("above", text="a b")],
        {"threshold": 0.5},
    )

    assert [item["candidateId"] for item in char_output] == ["pass"]
    assert [item["candidateId"] for item in unique_output] == ["above"]
    assert unique_rejected == ["equal"]


def test_hash_deduplicate_is_first_wins_and_uses_upstream_multifield_encoding() -> None:
    invocation = translate_dataflow_alias(
        DATAFLOW_ALIAS_SOURCE_IDS["HashDeduplicate"],
        {"hash_func": "sha256"},
        {"input_keys": ["title", "text"], "output_key": "unique"},
    )
    executor = COMPAT_EXECUTORS[(invocation.operator_id, invocation.pack_version)]
    items = [
        _candidate("first", title="T", text="body"),
        _candidate("second", title="T", text="body"),
        _candidate("third", title="title:\nT\ntext", text="body"),
    ]
    original = copy.deepcopy(items)

    output, metrics, rejected = executor(items, invocation.config)

    assert [item["candidateId"] for item in output] == ["first", "third"]
    assert output[0]["normalizedData"]["unique"] == 1
    assert rejected == ["second"]
    assert metrics["duplicateCount"] == 1
    assert items == original


@pytest.mark.parametrize(
    ("alias", "text", "expected"),
    [
        (
            "TextNormalization",
            "On January 2, 2024 pay $ 12 after 3/4/25.",
            "On 2024-01-02 pay 12 USD after 25-4-3.",
        ),
        ("RemoveImageRefs", "before ![](images/a.jpg) after", "before  after"),
    ],
)
def test_phase2_refiners_match_pinned_text_semantics(
    alias: str, text: str, expected: str
) -> None:
    output, _, rejected = _invoke(alias, [_candidate("one", text=text)])

    assert output[0]["normalizedData"]["text"] == expected
    assert rejected == []


@pytest.mark.parametrize(
    ("alias", "init", "passing", "rejected"),
    [
        ("ColonEnd", {}, "complete", "heading:"),
        (
            "LineEndWithEllipsis",
            {"threshold": 0.5},
            "one...\ntwo\nthree",
            "one...\ntwo",
        ),
        ("CurlyBracket", {"threshold": 0.2}, "abc{def", "{{abc"),
        ("CapitalWords", {"threshold": 0.5}, "OK lower", "OK YES"),
        (
            "LineStartWithBulletpoint",
            {"threshold": 0.5},
            "• one\ntwo",
            "• one\n• two",
        ),
    ],
)
def test_phase2_rules_preserve_strict_and_inclusive_boundaries(
    alias: str, init: dict[str, object], passing: str, rejected: str
) -> None:
    output, _, rejected_ids = _invoke(
        alias,
        [_candidate("pass", text=passing), _candidate("reject", text=rejected)],
        init,
    )

    assert [item["candidateId"] for item in output] == ["pass"]
    assert rejected_ids == ["reject"]


@pytest.mark.parametrize(
    ("alias", "init", "kept"),
    [
        ("LineEndWithEllipsis", {}, False),
        ("SymbolWordRatio", {}, False),
        ("AlphaWords", {"threshold": 0.5, "use_tokenizer": False}, False),
        ("NoPunc", {}, True),
        ("MeanWordLength", {}, False),
        ("StopWord", {"threshold": 0.5, "use_tokenizer": False}, False),
        ("CapitalWords", {}, True),
    ],
)
def test_phase2_rules_match_upstream_for_whitespace_only_text(
    alias: str, init: dict[str, object], kept: bool
) -> None:
    output, _, rejected = _invoke(
        alias,
        [_candidate("blank", text=" \n\t ")],
        init,
    )

    assert ([item["candidateId"] for item in output] == ["blank"]) is kept
    assert (rejected == []) is kept


def test_blocklist_uses_pinned_assets_and_inclusive_threshold() -> None:
    items = [
        _candidate("one-hit", text="anal"),
        _candidate("two-hits", text="anal anus"),
    ]
    original = copy.deepcopy(items)

    output, metrics, rejected = _invoke("Blocklist", items)

    assert [item["candidateId"] for item in output] == ["one-hit"]
    assert output[0]["normalizedData"]["blocklist_filter_label"] == 1
    assert metrics["rejectedInputCount"] == 1
    assert rejected == ["two-hits"]
    assert items == original


def test_ngram_hash_deduplicate_uses_upstream_chunk_overlap_semantics() -> None:
    output, metrics, rejected = _invoke(
        "NgramHashDeduplicate",
        [
            _candidate("first", text="abcdef"),
            _candidate("overlap", text="abXYzz"),
            _candidate("distinct", text="ghijkl"),
        ],
        {"n_gram": 3, "hash_func": "sha256", "diff_size": 1},
    )

    assert [item["candidateId"] for item in output] == ["first", "distinct"]
    assert rejected == ["overlap"]
    assert metrics["duplicateCount"] == 1


@pytest.mark.parametrize(
    ("alias", "init", "run"),
    [
        ("Lowercase", {"surprise": True}, {"input_key": "text"}),
        ("WordNumber", {}, {}),
        (
            "HashDeduplicate",
            {},
            {"input_key": "text", "input_keys": ["text", "title"]},
        ),
        ("HashDeduplicate", {}, {"input_keys": ["text"]}),
    ],
)
def test_unsupported_alias_configs_fail_closed(
    alias: str, init: dict[str, object], run: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        translate_dataflow_alias(DATAFLOW_ALIAS_SOURCE_IDS[alias], init, run)


@pytest.mark.parametrize("fields", [[], ["title", "text"]])
def test_rule_filter_requires_exactly_one_field(fields: list[str]) -> None:
    executor = COMPAT_EXECUTORS[("text.rule-filter", COMPAT_PACK_VERSION)]
    items = [_candidate("only", text="hello world")]
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        executor(items, {"fields": fields})


def test_deduplicate_requires_at_least_one_field() -> None:
    executor = COMPAT_EXECUTORS[("text.deduplicate", COMPAT_PACK_VERSION)]
    with pytest.raises(ValueError, match="dataflow_operator_unsupported"):
        executor([_candidate("only", text="x")], {"fields": []})


def test_deduplicate_treats_missing_fields_as_empty_text() -> None:
    executor = COMPAT_EXECUTORS[("text.deduplicate", COMPAT_PACK_VERSION)]
    items = [
        _candidate("first", title="T"),
        _candidate("second", title="T"),
        _candidate("third", title="T", content="body"),
    ]
    output, metrics, rejected = executor(items, {"fields": ["title", "content"]})

    assert [item["candidateId"] for item in output] == ["first", "third"]
    assert rejected == ["second"]
    assert metrics["duplicateCount"] == 1
