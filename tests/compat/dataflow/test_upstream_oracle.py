"""Opt-in oracle against the actual SHA-pinned OpenDCAI/DataFlow checkout.

Normal CI uses the reviewed golden fixture and never installs DataFlow's heavy
dependency tree. To audit or refresh the fixture, point ``DATAFLOW_UPSTREAM_ROOT``
at the pinned checkout and set ``DATAFLOW_RUN_UPSTREAM_ORACLE=1``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "dataflow"
    / "pinned_f62aa134_golden.json"
)
_GOLDEN = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
_PHASE2_FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "fixtures"
    / "dataflow"
    / "pinned_f62aa134_phase2_golden.json"
)
_PHASE2_GOLDEN = json.loads(_PHASE2_FIXTURE_PATH.read_text(encoding="utf-8"))
_ENABLED = os.environ.get("DATAFLOW_RUN_UPSTREAM_ORACLE") == "1"
_ROOT_VALUE = os.environ.get("DATAFLOW_UPSTREAM_ROOT")

pytestmark = pytest.mark.skipif(
    not _ENABLED,
    reason=(
        "upstream DataFlow oracle is isolated; set "
        "DATAFLOW_RUN_UPSTREAM_ORACLE=1 and DATAFLOW_UPSTREAM_ROOT"
    ),
)


class _FrameStorage:
    """Small storage double implementing only the upstream operators' seam."""

    def __init__(self, frame):
        self.frame = frame

    def read(self, output_type):
        assert output_type == "dataframe"
        return self.frame.copy(deep=True)

    def write(self, frame):
        self.frame = frame.copy(deep=True)
        return "in-memory-oracle"


def _verified_upstream_root() -> Path:
    if not _ROOT_VALUE:
        pytest.skip("DATAFLOW_UPSTREAM_ROOT is required for the upstream oracle")
    root = Path(_ROOT_VALUE).resolve()
    if not root.is_dir():
        pytest.fail(f"DATAFLOW_UPSTREAM_ROOT is not a directory: {root}")

    source_sha = _GOLDEN["upstream"]["sourceSha"]
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != source_sha:
        pytest.fail(f"DataFlow checkout HEAD must be {source_sha}, got {head}")

    mismatches = []
    for relative, expected in _GOLDEN["upstream"]["files"].items():
        blob = subprocess.run(
            ["git", "-C", str(root), "show", f"{source_sha}:{relative}"],
            check=False,
            capture_output=True,
        )
        actual = (
            hashlib.sha256(blob.stdout).hexdigest()
            if blob.returncode == 0
            else "<missing>"
        )
        if actual != expected:
            mismatches.append(f"{relative}: expected {expected}, got {actual}")
    if mismatches:
        pytest.fail("DataFlow checkout does not match pinned source:\n" + "\n".join(mismatches))
    return root


def _import_class(dotted_name: str):
    module_name, class_name = dotted_name.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _rows(case):
    return [
        {
            "candidateId": item["candidateId"],
            "content": item["normalizedData"]["content"],
            "lineage": item["lineage"],
        }
        for item in case["items"]
    ]


def _expected_rows(case):
    return [
        {
            "candidateId": candidate_id,
            **normalized,
            "lineage": lineage,
        }
        for candidate_id, normalized, lineage in zip(
            case["expected"]["candidateIds"],
            case["expected"]["normalizedData"],
            case["expected"]["lineage"],
            strict=True,
        )
    ]


def _phase2_aliases():
    return {item["alias"]: item for item in _PHASE2_GOLDEN["aliases"]}


def test_actual_pinned_upstream_operators_reproduce_the_reviewed_goldens():
    root = _verified_upstream_root()
    sys.path.insert(0, str(root))
    try:
        try:
            pandas = importlib.import_module("pandas")
            html_entity = _import_class(
                "dataflow.operators.general_text.refine.html_entity_refiner."
                "HtmlEntityRefiner"
            )
            html_url = _import_class(
                "dataflow.operators.general_text.refine.html_url_remover_refiner."
                "HtmlUrlRemoverRefiner"
            )
            lowercase = _import_class(
                "dataflow.operators.general_text.refine.lowercase_refiner."
                "LowercaseRefiner"
            )
            remove_emoji = _import_class(
                "dataflow.operators.general_text.refine.remove_emoji_refiner."
                "RemoveEmojiRefiner"
            )
            remove_number = _import_class(
                "dataflow.operators.general_text.refine.remove_number_refiner."
                "RemoveNumberRefiner"
            )
            remove_punctuation = _import_class(
                "dataflow.operators.general_text.refine.remove_punctuation_refiner."
                "RemovePunctuationRefiner"
            )
            remove_spaces = _import_class(
                "dataflow.operators.general_text.refine.remove_extra_spaces_refiner."
                "RemoveExtraSpacesRefiner"
            )
            word_number = _import_class(
                "dataflow.operators.general_text.filter.word_number_filter."
                "WordNumberFilter"
            )
            hash_deduplicate = _import_class(
                "dataflow.operators.general_text.filter.hash_deduplicate_filter."
                "HashDeduplicateFilter"
            )
        except ImportError as error:
            pytest.skip(f"pinned DataFlow dependencies are not installed: {error}")

        cases = {case["id"]: case for case in _GOLDEN["goldenCases"]}

        clean_case = cases["text-clean-sequence"]
        clean_storage = _FrameStorage(pandas.DataFrame(_rows(clean_case)))
        for operator in (
            html_entity(html_entities=["nbsp", "amp"]),
            html_url(),
            lowercase(),
            remove_emoji(),
            remove_number(),
            remove_punctuation(),
            remove_spaces(),
        ):
            operator.run(clean_storage, input_key="content")
        assert clean_storage.frame.to_dict(orient="records") == _expected_rows(clean_case)

        filter_case = cases["rule-filter-stable-order"]
        filter_storage = _FrameStorage(pandas.DataFrame(_rows(filter_case)))
        word_number(min_words=2, max_words=10).run(
            filter_storage,
            input_key="content",
            output_key="word_number_filter_label",
        )
        assert filter_storage.frame.to_dict(orient="records") == _expected_rows(
            filter_case
        )

        dedupe_case = cases["hash-deduplicate-first-occurrence"]
        dedupe_storage = _FrameStorage(pandas.DataFrame(_rows(dedupe_case)))
        hash_deduplicate(hash_func="md5").run(
            dedupe_storage,
            input_key="content",
            output_key="minhash_deduplicated_label",
        )
        assert dedupe_storage.frame.to_dict(orient="records") == _expected_rows(
            dedupe_case
        )
    finally:
        sys.path.remove(str(root))


def test_actual_pinned_upstream_phase2_goldens():
    root = _verified_upstream_root()
    sys.path.insert(0, str(root))
    try:
        try:
            pandas = importlib.import_module("pandas")
            aliases = _phase2_aliases()
            classes = {
                alias: _import_class(spec["dotted"])
                for alias, spec in aliases.items()
            }
        except ImportError as error:
            pytest.skip(f"pinned DataFlow dependencies are not installed: {error}")

        for case in _PHASE2_GOLDEN["ruleBoundaryCases"]:
            alias = case["alias"]
            rows = [
                {"content": text, "_oracleIndex": index}
                for index, text in enumerate(case["accepted"] + case["rejected"])
            ]
            storage = _FrameStorage(pandas.DataFrame(rows))
            classes[alias](**case["initConfig"]).run(
                storage,
                input_key="content",
            )
            assert storage.frame["content"].tolist() == case["accepted"], case["id"]

        blank_expectations = {
            "LineEndWithEllipsis": False,
            "SymbolWordRatio": False,
            "AlphaWords": False,
            "NoPunc": True,
            "MeanWordLength": False,
            "StopWord": False,
            "CapitalWords": True,
        }
        for alias, kept in blank_expectations.items():
            spec = aliases[alias]
            storage = _FrameStorage(
                pandas.DataFrame([{"content": " \n\t ", "_oracleIndex": 0}])
            )
            classes[alias](**spec["initConfig"]).run(
                storage,
                input_key="content",
            )
            assert (storage.frame["content"].tolist() == [" \n\t "]) is kept, alias

        for case in _PHASE2_GOLDEN["cleanGoldenCases"]:
            storage = _FrameStorage(pandas.DataFrame([{"content": case["input"]}]))
            classes[case["alias"]]().run(storage, input_key="content")
            assert storage.frame["content"].tolist() == [case["expected"]], case["id"]

        for case in _PHASE2_GOLDEN["blocklistCases"]:
            rows = [
                {"content": text}
                for text in case["accepted"] + case["rejected"]
            ]
            storage = _FrameStorage(pandas.DataFrame(rows))
            classes["Blocklist"](
                language=case["language"],
                threshold=case["threshold"],
                use_tokenizer=False,
            ).run(storage, input_key="content")
            assert storage.frame["content"].tolist() == case["accepted"], case["id"]

        for case in _PHASE2_GOLDEN["ngramHashCases"]:
            rows = [
                {"content": text, "_oracleIndex": index}
                for index, text in enumerate(case["contents"])
            ]
            storage = _FrameStorage(pandas.DataFrame(rows))
            classes["NgramHashDeduplicate"](
                n_gram=case["nGram"],
                hash_func="md5",
                diff_size=case["diffSize"],
            ).run(storage, input_key="content")
            assert storage.frame["_oracleIndex"].tolist() == case[
                "selectedIndexes"
            ], case["id"]
    finally:
        sys.path.remove(str(root))
