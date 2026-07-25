"""Pinned, dependency-free compatibility for a small DataFlow operator subset."""

from __future__ import annotations

import base64
import copy
import hashlib
import re
import string
import unicodedata
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any

DATAFLOW_COMPAT_SHA = "f62aa1349e0ff14cb737a4cbda1945d04fde85bb"
COMPAT_PACK_ID = "builtin.text-cleaning"
COMPAT_PACK_VERSION = "1.1.0"

_Executor = Callable[
    [list[dict[str, Any]], dict[str, Any]],
    tuple[list[dict[str, Any]], dict[str, Any], list[str]],
]


@dataclass(frozen=True)
class DataFlowInvocation:
    operator_id: str
    pack_id: str
    pack_version: str
    kind: str
    config: dict[str, Any]
    source_id: str

    def to_params(self) -> dict[str, Any]:
        return {
            "operatorId": self.operator_id,
            "packId": self.pack_id,
            "packVersion": self.pack_version,
            "config": copy.deepcopy(self.config),
        }


COMPAT_OPERATOR_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "operatorId": "text.clean",
        "kind": "refine",
        "packId": COMPAT_PACK_ID,
        "packVersion": COMPAT_PACK_VERSION,
        "label": "Text clean",
        "description": "Apply pinned DataFlow-compatible deterministic text cleaners.",
        "configKeys": ["fields", "operations", "htmlEntities"],
        "inputPort": "recordCandidate[]",
        "outputPort": "recordCandidate[]",
        "deterministic": True,
    },
    {
        "operatorId": "text.rule-filter",
        "kind": "filter",
        "packId": COMPAT_PACK_ID,
        "packVersion": COMPAT_PACK_VERSION,
        "label": "Text rule filter",
        "description": "Apply pinned DataFlow-compatible deterministic text rules.",
        "configKeys": ["fields", "rules"],
        "inputPort": "recordCandidate[]",
        "outputPort": "recordCandidate[]",
        "deterministic": True,
    },
    {
        "operatorId": "text.deduplicate",
        "kind": "filter",
        "packId": COMPAT_PACK_ID,
        "packVersion": COMPAT_PACK_VERSION,
        "label": "Text deduplicate",
        "description": "Keep the first record for each pinned DataFlow-compatible hash.",
        "configKeys": [
            "fields",
            "hashFunction",
            "mode",
            "nGram",
            "diffSize",
            "outputKey",
        ],
        "inputPort": "recordCandidate[]",
        "outputPort": "recordCandidate[]",
        "deterministic": True,
    },
)

_SOURCE_PREFIX = f"dataflow@{DATAFLOW_COMPAT_SHA}::"
_ALIASES = {
    "RemoveExtraSpaces": (
        "dataflow.operators.general_text.refine.remove_extra_spaces_refiner."
        "RemoveExtraSpacesRefiner"
    ),
    "Lowercase": (
        "dataflow.operators.general_text.refine.lowercase_refiner.LowercaseRefiner"
    ),
    "HtmlUrlRemover": (
        "dataflow.operators.general_text.refine.html_url_remover_refiner."
        "HtmlUrlRemoverRefiner"
    ),
    "HtmlEntity": (
        "dataflow.operators.general_text.refine.html_entity_refiner.HtmlEntityRefiner"
    ),
    "RemoveEmoji": (
        "dataflow.operators.general_text.refine.remove_emoji_refiner.RemoveEmojiRefiner"
    ),
    "RemoveNumber": (
        "dataflow.operators.general_text.refine.remove_number_refiner.RemoveNumberRefiner"
    ),
    "RemovePunctuation": (
        "dataflow.operators.general_text.refine.remove_punctuation_refiner."
        "RemovePunctuationRefiner"
    ),
    "RemoveRepetitionsPunctuation": (
        "dataflow.operators.general_text.refine."
        "remove_repetitions_punctuation_refiner.RemoveRepetitionsPunctuationRefiner"
    ),
    "ContentNull": (
        "dataflow.operators.general_text.filter.rule_based_filter.ContentNullFilter"
    ),
    "WordNumber": (
        "dataflow.operators.general_text.filter.word_number_filter.WordNumberFilter"
    ),
    "SentenceNumber": (
        "dataflow.operators.general_text.filter.rule_based_filter.SentenceNumberFilter"
    ),
    "CharNumber": (
        "dataflow.operators.general_text.filter.rule_based_filter.CharNumberFilter"
    ),
    "UniqueWords": (
        "dataflow.operators.general_text.filter.rule_based_filter.UniqueWordsFilter"
    ),
    "HashDeduplicate": (
        "dataflow.operators.general_text.filter.hash_deduplicate_filter."
        "HashDeduplicateFilter"
    ),
    "ColonEnd": (
        "dataflow.operators.general_text.filter.rule_based_filter.ColonEndFilter"
    ),
    "LineEndWithEllipsis": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "LineEndWithEllipsisFilter"
    ),
    "SymbolWordRatio": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "SymbolWordRatioFilter"
    ),
    "AlphaWords": (
        "dataflow.operators.general_text.filter.rule_based_filter.AlphaWordsFilter"
    ),
    "HtmlEntityFilter": (
        "dataflow.operators.general_text.filter.rule_based_filter.HtmlEntityFilter"
    ),
    "IDCard": (
        "dataflow.operators.general_text.filter.rule_based_filter.IDCardFilter"
    ),
    "NoPunc": (
        "dataflow.operators.general_text.filter.rule_based_filter.NoPuncFilter"
    ),
    "SpecialCharacter": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "SpecialCharacterFilter"
    ),
    "Watermark": (
        "dataflow.operators.general_text.filter.rule_based_filter.WatermarkFilter"
    ),
    "MeanWordLength": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "MeanWordLengthFilter"
    ),
    "StopWord": (
        "dataflow.operators.general_text.filter.rule_based_filter.StopWordFilter"
    ),
    "CurlyBracket": (
        "dataflow.operators.general_text.filter.rule_based_filter.CurlyBracketFilter"
    ),
    "CapitalWords": (
        "dataflow.operators.general_text.filter.rule_based_filter.CapitalWordsFilter"
    ),
    "LoremIpsum": (
        "dataflow.operators.general_text.filter.rule_based_filter.LoremIpsumFilter"
    ),
    "LineStartWithBulletpoint": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "LineStartWithBulletpointFilter"
    ),
    "LineWithJavascript": (
        "dataflow.operators.general_text.filter.rule_based_filter."
        "LineWithJavascriptFilter"
    ),
    "TextNormalization": (
        "dataflow.operators.general_text.refine.text_normalization_refiner."
        "TextNormalizationRefiner"
    ),
    "RemoveImageRefs": (
        "dataflow.operators.general_text.refine.remove_image_ref_refiner."
        "RemoveImageRefsRefiner"
    ),
    "Blocklist": (
        "dataflow.operators.general_text.filter.blocklist_filter.BlocklistFilter"
    ),
    "NgramHashDeduplicate": (
        "dataflow.operators.general_text.filter.ngramhash_deduplicate_filter."
        "NgramHashDeduplicateFilter"
    ),
}
DATAFLOW_ALIAS_SOURCE_IDS = {
    alias: _SOURCE_PREFIX + dotted_name for alias, dotted_name in _ALIASES.items()
}
_ALIAS_BY_SOURCE_ID = {
    source_id: alias for alias, source_id in DATAFLOW_ALIAS_SOURCE_IDS.items()
}

_CLEAN_OPERATIONS = {
    "RemoveExtraSpaces": "removeExtraSpaces",
    "Lowercase": "lowercase",
    "HtmlUrlRemover": "htmlUrlRemover",
    "HtmlEntity": "htmlEntity",
    "RemoveEmoji": "removeEmoji",
    "RemoveNumber": "removeNumber",
    "RemovePunctuation": "removePunctuation",
    "RemoveRepetitionsPunctuation": "removeRepetitionsPunctuation",
    "TextNormalization": "textNormalization",
    "RemoveImageRefs": "removeImageRefs",
}
_DEFAULT_HTML_ENTITIES = [
    "nbsp",
    "lt",
    "gt",
    "amp",
    "quot",
    "apos",
    "hellip",
    "ndash",
    "mdash",
    "lsquo",
    "rsquo",
    "ldquo",
    "rdquo",
]

# Pinned OpenDCAI/DataFlow blocklists, Apache-2.0 with the upstream repository.
# The compressed bytes are the exact git blobs at DATAFLOW_COMPAT_SHA.
_BLOCKLIST_ASSETS = {
    "en": (
        "af851ecef1d5f212caba17339b12ac39cc2fef7d78c74876f67237644fcee8bd",
        "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",
    ),
    "zh": (
        "a1d9aa037c8b039ef3b40148b3364ce2ca62ce4a955b7082a16ad99f6cbd1bc0",
        "eNpNlslyIjkQhu96mIno6EufPYc5zWleZo7s+9bgMTsGYxZjm8Vgs5uHabTUrR9h/szKAkdQ9f2pUkmpVKaKb9//UN++28hWnTdpuxvZdBIqS0Y0QsqtFsDEhcL6tWQbMXXets1mAyzpOu8eCfpxRTCpE2P54JIh8z5ReOzF8+q8T7heFbjTgw/8ropH9I1xLTCGKcGvWNoWsjr+7JpZadKtuaig97hG8J5euOHYhbc6sjezWza+PtHxsZ5+sLpOTsb2Sx+anBE00PgMne/pwTEwyiNW0+iXrtPodSBTm3mb3kW9kpKnOtywqYUSLwEvdFA6kfMifaCphxWlk/D2mVF8ZaxXBJeBlWro3ZBgaxPslNK5uG1Mlc6Had+wlzp/d0M3Hh5YY6T8O13YRKWLOb2c68+p9/AIo097CLjIDHjWu4zSpaheFICC3mG+0tZOMUKvwzF8CRQC4yszy4uyqY0oSphN6mpwn8eYHiyBO6+G1TyOAodYmWWPFILGa0WWXHbJJjJsUN/Bhi4MCmwlIXzFob3sJRpu6IZ0CMjhYMUOsRG8N0xJg1gAv8ZbQxsyrLDvw4pXfwCWX+aEcVV+GkP5ixYjcGpUo1LRo74bnADs4rgWeCZvPmV4nQwd33PbM9L8wJhics45Xvcl+/QsYVYdpecxjsw8Zt8+gaLUJlQQa1Yc63kxyJ950UXS9q1Myps02BtWbjViJXvCirJaL8K2dSC4CFlwYJFTej2mY0Fv3/7l5Ni+nTdRTmMocotBFSZKOl0TxDfSM1J+WAPld72EVQyElZSJjKWDae1MYc7qdf/nPyL++luEeAGFQJoWDYNqOew4qxjUw4RGdFFdALo+Jphq10WPpKh2TTTu0m/A8rzJ8DvJBHkBh0XBH5Ms/6AbhYBQZJj/6sqkSufdDvhpKnmqmwF2tooCRtfzvq9MGi+lgYqNTAlev4OlKZM5mmJZmSwfEpA8dbEsSzPlsp6flD+mQA49MfzjVwxy1lfk7BdHxKAavvSRuMNA3AXXsWWzRPnDQV2Hk40hhewCqLDM7afL95SpDuQgJ0WeM3hAVuTI5WngSHVg0ltlWim7LwI7jjKARKXJ8Hud4KdMO2JH6P8+4Q1Y83XeLgh6mCSYfp4xXxHs6EhgzwAUqtmevFARdaYTcddHVpxCSABlw2MJHj6WVCoALcummspmq6gOAhwl2OxBqtkW0qb9rq5fNltp6XGUqpPUU4JHrLRoeVKhtn6k7zGhumLUe0qCa0dhymT7Muax3j5pIATpvMsR9M+lkpABMh6U1LmvyHkcAbofJiAcPAapMsEe2kARV5OKwkUGFBUUAEXBZRbmHnPg64houiWer9p4CVjc0I0yHeA5VgfZWPfevO4lDCrm2sk3+lI/7jilwnSntcvPFEUWl+mulZcs0Cnk1ZCBa4IrFYCVvk0STGrN6G4YsybB5biLF64womPlNTuULF67q3NVAs0O0EcMcNEcIz5X3tOHfPpEwTlf8Sus+C1W8um7GNzHj7aEGuDVvBx4zE3vB90ogQn44BNKIwYCIMcvQJ9/OYK9z3sdO9E+kcIZ/3u8LCuvPneFO/WrU8Vpvae2jPKWT+p3b9mB9YGjp9ygZiT8PbrfTYI/Z7q8QS17xXv8BWkEitvOhw9pM9kC5ZmeDZFnaRfHobko6NNRuV3b1hfKX69XTYii3LvGwPZeXKKr/gdO9p9p",
    ),
}

# NLTK's English stopwords corpus is an unpinned upstream runtime dependency.
# Freeze the observed 198-word corpus locally so compatibility never downloads data.
_NLTK_STOPWORDS_ASSET = (
    "f6d005956f407dbc6ea32e5ff0c7e8e6f71488d3239b9023efdc7fc139d6375b",
    "eNo1U1uSxCAI/OciOZeZmJGtKFs+1vL2240zVdAQRJ4mSDhtdOJflHD3WCW8g5aNDSfUn0dClgCtXOAloUZycTjg1SR0OSPoFUajxOEZb6vUtbyBj01gn35kPcmJzOeSFwK/bDzXVyDgJZc6FwdaDBSbQ9noVsa+jJb9PaGOSmsMryR3nIIq5K6W5R61J7SYwkUuDriVUD+4OPg3pkEoG7eJMRPs8bgIGIrHipW22hzic/MMH5rJ26D4RvMqiqt6Q+CyHlkwXC3dBA6K9OrZlUTH7m4d0bQ7M5geqO1nYDU4zJKD5ChZ36mXj0CIzLlng1OGZ9lI+wJ5mBIj+neEvRiogqlOMbEbBC6gVwQ8S+BgPj4bzs0hPn+RWhc8Idgxf+Ru0gLqagm7JSBHS/zm8NqeXvNBtcSdf0T5Svenxm6bgRhtYKFdOoMCXPMZoSqy1o2NIjt8yoPKK1wVsDkuB5TjYkdZx/ZYTNu5t57M3auNN5IbyGSUC62O0vWR8SvwRetLJp7R5DOa+xnNCEKC6e0CKw0fKBvdjdkmG5qsc3qdMym6BT7UjZwByKIMpvh/JtYz/dnPPbz5nd2SZYOM7ETcWNwadcRevr2113d/FQ6KDijmH2pQY+Y=",
)


def translate_dataflow_alias(
    source_id: str,
    init_config: Mapping[str, Any] | None = None,
    run_config: Mapping[str, Any] | None = None,
) -> DataFlowInvocation:
    """Translate one exact, SHA-locked upstream class into a native invocation."""

    alias = _ALIAS_BY_SOURCE_ID.get(source_id)
    if alias is None:
        _unsupported("source id is not in the pinned compatibility allowlist")
    init = _mapping(init_config, "init_config")
    run = _mapping(run_config, "run_config")

    if alias in _CLEAN_OPERATIONS:
        allowed_init = {"html_entities"} if alias == "HtmlEntity" else set()
        _only_keys(init, allowed_init, alias)
        _only_keys(run, {"input_key"}, alias)
        field = _required_string(run, "input_key")
        config: dict[str, Any] = {
            "fields": [field],
            "operations": [_CLEAN_OPERATIONS[alias]],
        }
        if alias == "HtmlEntity":
            config["htmlEntities"] = _string_list(
                init.get("html_entities", _DEFAULT_HTML_ENTITIES), "html_entities"
            )
        return _invocation("text.clean", "refine", config, source_id)

    if alias == "HashDeduplicate":
        _only_keys(init, {"hash_func"}, alias)
        _only_keys(run, {"input_key", "input_keys", "output_key"}, alias)
        hash_function = init.get("hash_func", "md5")
        if hash_function not in {"md5", "sha256", "xxh3"}:
            _unsupported("HashDeduplicate hash_func must be md5, sha256, or xxh3")
        has_one = run.get("input_key") is not None
        has_many = run.get("input_keys") is not None
        if has_one == has_many:
            _unsupported("HashDeduplicate requires exactly one of input_key or input_keys")
        if has_many:
            fields = _string_list(run["input_keys"], "input_keys")
            if len(fields) < 2:
                _unsupported("HashDeduplicate input_keys requires at least two fields")
        else:
            fields = [_required_string(run, "input_key")]
        return _invocation(
            "text.deduplicate",
            "filter",
            {
                "fields": fields,
                "hashFunction": hash_function,
                "outputKey": _optional_string(
                    run, "output_key", "minhash_deduplicated_label"
                ),
            },
            source_id,
        )

    if alias == "NgramHashDeduplicate":
        _only_keys(init, {"n_gram", "hash_func", "diff_size"}, alias)
        _only_keys(run, {"input_key", "input_keys", "output_key"}, alias)
        hash_function = init.get("hash_func", "md5")
        if hash_function not in {"md5", "sha256"}:
            _unsupported(
                "NgramHashDeduplicate hash_func must be md5 or sha256; "
                "xxh3 is unavailable without an explicit dependency"
            )
        has_one = run.get("input_key") is not None
        has_many = run.get("input_keys") is not None
        if has_one == has_many:
            _unsupported(
                "NgramHashDeduplicate requires exactly one of input_key or input_keys"
            )
        if has_many:
            fields = _string_list(run["input_keys"], "input_keys")
            if len(fields) < 2:
                _unsupported("NgramHashDeduplicate input_keys requires at least two fields")
        else:
            fields = [_required_string(run, "input_key")]
        return _invocation(
            "text.deduplicate",
            "filter",
            {
                "fields": fields,
                "mode": "ngramHash",
                "nGram": _integer(init.get("n_gram", 3), "n_gram"),
                "hashFunction": hash_function,
                "diffSize": _integer(init.get("diff_size", 1), "diff_size"),
                "outputKey": _optional_string(
                    run, "output_key", "minhash_deduplicated_label"
                ),
            },
            source_id,
        )

    _only_keys(run, {"input_key", "output_key"}, alias)
    field = _required_string(run, "input_key")
    if alias == "ContentNull":
        _only_keys(init, set(), alias)
        rule = {
            "type": "contentNull",
            "outputKey": _optional_string(
                run, "output_key", "content_null_filter_label"
            ),
        }
    elif alias == "WordNumber":
        _only_keys(init, {"min_words", "max_words"}, alias)
        rule = {
            "type": "wordNumber",
            "min": _integer(init.get("min_words", 20), "min_words"),
            "max": _integer(init.get("max_words", 100000), "max_words"),
            "outputKey": _optional_string(
                run, "output_key", "word_number_filter_label"
            ),
        }
    elif alias == "SentenceNumber":
        _only_keys(init, {"min_sentences", "max_sentences"}, alias)
        rule = {
            "type": "sentenceNumber",
            "min": _integer(init.get("min_sentences", 3), "min_sentences"),
            "max": _integer(init.get("max_sentences", 7500), "max_sentences"),
            "outputKey": _optional_string(
                run, "output_key", "sentence_number_filter_label"
            ),
        }
    elif alias == "CharNumber":
        _only_keys(init, {"threshold"}, alias)
        rule = {
            "type": "charNumber",
            "threshold": _integer(init.get("threshold", 100), "threshold"),
            "outputKey": _optional_string(
                run, "output_key", "char_number_filter_label"
            ),
        }
    elif alias == "UniqueWords":
        _only_keys(init, {"threshold"}, alias)
        rule = {
            "type": "uniqueWords",
            "threshold": _number(init.get("threshold", 0.1), "threshold"),
            "outputKey": _optional_string(run, "output_key", "unique_words_filter"),
        }
    else:
        rule = _translate_phase2_rule(alias, init, run)
    return _invocation(
        "text.rule-filter", "filter", {"fields": [field], "rules": [rule]}, source_id
    )


def _translate_phase2_rule(
    alias: str, init: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    output_defaults = {
        "ColonEnd": "colonendfilter_label",
        "LineEndWithEllipsis": "line_end_with_ellipsis_filter_label",
        "SymbolWordRatio": "symbol_word_ratio_filter_label",
        "AlphaWords": "alpha_words_filter_label",
        "HtmlEntityFilter": "html_entity_filter_label",
        "IDCard": "id_card_filter_label",
        "NoPunc": "no_punc_filter_label",
        "SpecialCharacter": "special_character_filter_label",
        "Watermark": "watermark_filter_label",
        "MeanWordLength": "mean_word_length_filter_label",
        "StopWord": "stop_word_filter_label",
        "CurlyBracket": "curly_bracket_filter_label",
        "CapitalWords": "capital_words_filter",
        "LoremIpsum": "loremipsum_filter_label",
        "LineStartWithBulletpoint": "line_start_with_bullet_point_filter_label",
        "LineWithJavascript": "line_with_javascript_filter_label",
        "Blocklist": "blocklist_filter_label",
    }
    rule_types = {
        "ColonEnd": "colonEnd",
        "LineEndWithEllipsis": "lineEndWithEllipsis",
        "SymbolWordRatio": "symbolWordRatio",
        "AlphaWords": "alphaWords",
        "HtmlEntityFilter": "htmlEntity",
        "IDCard": "idCard",
        "NoPunc": "noPunc",
        "SpecialCharacter": "specialCharacter",
        "Watermark": "watermark",
        "MeanWordLength": "meanWordLength",
        "StopWord": "stopWord",
        "CurlyBracket": "curlyBracket",
        "CapitalWords": "capitalWords",
        "LoremIpsum": "loremIpsum",
        "LineStartWithBulletpoint": "lineStartWithBulletpoint",
        "LineWithJavascript": "lineWithJavascript",
        "Blocklist": "blocklist",
    }
    if alias not in rule_types:
        _unsupported("alias has no pinned compatibility translation")
    output_key = _optional_string(run, "output_key", output_defaults[alias])
    rule: dict[str, Any] = {"type": rule_types[alias], "outputKey": output_key}

    if alias in {"ColonEnd", "HtmlEntityFilter", "SpecialCharacter"}:
        _only_keys(init, set(), alias)
    elif alias in {
        "LineEndWithEllipsis",
        "SymbolWordRatio",
        "IDCard",
        "NoPunc",
        "CurlyBracket",
        "LoremIpsum",
        "LineStartWithBulletpoint",
        "LineWithJavascript",
    }:
        _only_keys(init, {"threshold"}, alias)
        defaults = {
            "LineEndWithEllipsis": 0.3,
            "SymbolWordRatio": 0.4,
            "IDCard": 3,
            "NoPunc": 112,
            "CurlyBracket": 0.025,
            "LoremIpsum": 3e-8,
            "LineStartWithBulletpoint": 0.9,
            "LineWithJavascript": 3,
        }
        default = defaults[alias]
        rule["threshold"] = (
            _integer(init.get("threshold", default), "threshold")
            if isinstance(default, int)
            else _number(init.get("threshold", default), "threshold")
        )
    elif alias in {"AlphaWords", "StopWord"}:
        _only_keys(init, {"threshold", "use_tokenizer"}, alias)
        if "threshold" not in init or "use_tokenizer" not in init:
            _unsupported(f"{alias} requires threshold and use_tokenizer")
        rule["threshold"] = _number(init["threshold"], "threshold")
        rule["useTokenizer"] = _boolean(init["use_tokenizer"], "use_tokenizer")
    elif alias == "Watermark":
        _only_keys(init, {"watermarks"}, alias)
        rule["watermarks"] = _string_list(
            init.get("watermarks", ["Copyright", "Watermark", "Confidential"]),
            "watermarks",
        )
    elif alias == "MeanWordLength":
        _only_keys(init, {"min_length", "max_length"}, alias)
        rule["minLength"] = _number(init.get("min_length", 3), "min_length")
        rule["maxLength"] = _number(init.get("max_length", 10), "max_length")
    elif alias == "CapitalWords":
        _only_keys(init, {"threshold", "use_tokenizer"}, alias)
        rule["threshold"] = _number(init.get("threshold", 0.2), "threshold")
        rule["useTokenizer"] = _boolean(
            init.get("use_tokenizer", False), "use_tokenizer"
        )
    elif alias == "Blocklist":
        _only_keys(init, {"language", "threshold", "use_tokenizer"}, alias)
        language = init.get("language", "en")
        if language not in _BLOCKLIST_ASSETS:
            _unsupported("Blocklist language must be en or zh")
        rule["language"] = language
        rule["threshold"] = _integer(init.get("threshold", 1), "threshold")
        rule["useTokenizer"] = _boolean(
            init.get("use_tokenizer", False), "use_tokenizer"
        )
    return rule


def _text_clean(
    items: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    _validate_items(items)
    _only_keys(config, {"fields", "operations", "htmlEntities"}, "text.clean")
    fields = _string_list(config.get("fields", ["title", "content"]), "fields")
    operations = _string_list(
        config.get("operations", ["removeExtraSpaces"]), "operations"
    )
    unknown = set(operations) - set(_CLEAN_OPERATIONS.values())
    if unknown:
        _unsupported(f"text.clean operation is unsupported: {sorted(unknown)[0]}")
    entities = _string_list(
        config.get("htmlEntities", _DEFAULT_HTML_ENTITIES), "htmlEntities"
    )
    output = copy.deepcopy(items)
    changed = 0
    for item in output:
        normalized = _normalized(item)
        for field in fields:
            value = normalized.get(field)
            if not isinstance(value, str):
                continue
            refined = value
            for operation in operations:
                refined = _clean_value(refined, operation, entities)
            changed += refined != value
            normalized[field] = refined
    return output, {"changedFieldCount": changed}, []


def _text_rule_filter(
    items: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    _validate_items(items)
    _only_keys(config, {"fields", "rules"}, "text.rule-filter")
    fields = _string_list(config.get("fields", ["content"]), "fields")
    if len(fields) != 1:
        _unsupported(
            "text.rule-filter supports exactly one field per invocation"
        )
    rules = config.get(
        "rules",
        [{"type": "contentNull", "outputKey": "content_null_filter_label"}],
    )
    if not isinstance(rules, list) or not rules or any(
        not isinstance(rule, dict) for rule in rules
    ):
        _unsupported("text.rule-filter rules must be a non-empty list of objects")
    output: list[dict[str, Any]] = []
    rejected: list[str] = []
    rule_hits: dict[str, int] = {}
    for item in copy.deepcopy(items):
        normalized = _normalized(item)
        accepted = True
        for rule in rules:
            passed, result = _apply_rule(normalized, fields[0], rule)
            if passed:
                normalized[_rule_output_key(rule)] = result
            else:
                accepted = False
                rule_type = str(rule.get("type"))
                rule_hits[rule_type] = rule_hits.get(rule_type, 0) + 1
        if accepted:
            output.append(item)
        else:
            _record_rejection(rejected, item)
    return output, {
        "ruleHits": rule_hits,
        "rejectedInputCount": len(items) - len(output),
    }, rejected


def _text_deduplicate(
    items: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    _validate_items(items)
    _only_keys(
        config,
        {"fields", "hashFunction", "mode", "nGram", "diffSize", "outputKey"},
        "text.deduplicate",
    )
    fields = _string_list(config.get("fields", ["title", "content"]), "fields")
    if not fields:
        _unsupported("text.deduplicate requires at least one field")
    mode = config.get("mode", "exact")
    if mode not in {"exact", "ngramHash"}:
        _unsupported("text.deduplicate mode must be exact or ngramHash")
    hash_function = config.get("hashFunction", "md5")
    output_key = _config_string(config, "outputKey", "minhash_deduplicated_label")
    if hash_function not in {"md5", "sha256", "xxh3"}:
        _unsupported("text.deduplicate hashFunction is unsupported")
    if mode == "ngramHash" and hash_function == "xxh3":
        _unsupported(
            "ngramHash xxh3 is unavailable without an explicit dependency"
        )
    if hash_function == "xxh3":
        try:
            from xxhash import xxh3_128  # type: ignore[import-not-found]
        except ImportError:
            _unsupported("xxh3 is unavailable in this installation")
        hasher: Callable[[bytes], Any] = xxh3_128
    else:
        hasher = getattr(hashlib, hash_function)

    output: list[dict[str, Any]] = []
    rejected: list[str] = []
    seen: set[str] = set()
    seen_ngrams: list[set[str]] = []
    n_gram = _integer(config.get("nGram", 3), "nGram")
    diff_size = _integer(config.get("diffSize", 1), "diffSize")
    if mode == "ngramHash" and n_gram <= 0:
        _unsupported("text.deduplicate nGram must be greater than zero")
    for item in copy.deepcopy(items):
        normalized = _normalized(item)
        if len(fields) > 1:
            text = "\n".join(
                f"{field}:\n{_string_field(normalized, field)}" for field in fields
            )
        else:
            text = _string_field(normalized, fields[0])
        if mode == "ngramHash":
            gram_length = len(text) // n_gram
            digests = {
                hasher(
                    text[index * gram_length : (index + 1) * gram_length].encode(
                        "utf-8"
                    )
                ).hexdigest()
                for index in range(n_gram)
            }
            if any(
                len(digests.intersection(previous)) >= diff_size
                for previous in seen_ngrams
            ):
                _record_rejection(rejected, item)
                continue
            seen_ngrams.append(digests)
        else:
            digest = hasher(text.encode("utf-8")).hexdigest()
            if digest in seen:
                _record_rejection(rejected, item)
                continue
            seen.add(digest)
        normalized[output_key] = 1
        output.append(item)
    return output, {
        "duplicateCount": len(items) - len(output),
        "rejectedInputCount": len(items) - len(output),
    }, rejected


COMPAT_EXECUTORS: dict[tuple[str, str], _Executor] = {
    ("text.clean", COMPAT_PACK_VERSION): _text_clean,
    ("text.rule-filter", COMPAT_PACK_VERSION): _text_rule_filter,
    ("text.deduplicate", COMPAT_PACK_VERSION): _text_deduplicate,
}


def _clean_value(value: str, operation: str, entities: list[str]) -> str:
    if operation == "removeExtraSpaces":
        return " ".join(value.split())
    if operation == "lowercase":
        return value.lower()
    if operation == "htmlUrlRemover":
        value = re.sub(r"https?:\/\/\S+[\r\n]*", "", value, flags=re.MULTILINE)
        return re.sub(r"<.*?>", "", value)
    if operation == "htmlEntity":
        patterns = [
            pattern
            for entity in entities
            for pattern in (
                f"&{entity};",
                f"＆{entity};",
                f"&{entity}；",
                f"＆{entity}；",
            )
        ]
        return re.sub("|".join(patterns), "", value)
    if operation == "removeEmoji":
        return re.sub(
            "["
            "\U0001f600-\U0001f64f"
            "\U0001f300-\U0001f5ff"
            "\U0001f680-\U0001f6ff"
            "\U0001f1e0-\U0001f1ff"
            "\u2702-\u27b0"
            "]+",
            "",
            value,
        )
    if operation == "removeNumber":
        return "".join(character for character in value if not character.isdigit())
    if operation == "removePunctuation":
        return value.translate(str.maketrans("", "", string.punctuation))
    if operation == "removeRepetitionsPunctuation":
        return re.sub(r"([^\w\s_])\1+|(_)\2+", r"\1\2", value)
    if operation == "textNormalization":
        refined = re.sub(
            r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", r"\3-\2-\1", value
        )
        date_patterns = (
            (r"\b(\w+)\s+(\d{1,2}),\s+(\d{4})\b", "%B %d, %Y"),
            (r"\b(\d{1,2})\s+(\w+)\s+(\d{4})\b", "%d %B %Y"),
        )
        for pattern, date_format in date_patterns:
            match = re.search(pattern, refined)
            if match is None:
                continue
            date_text = match.group(0)
            try:
                normalized_date = datetime.strptime(
                    date_text, date_format
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue
            refined = refined.replace(date_text, normalized_date)
        return re.sub(r"\$\s?(\d+)", r"\1 USD", refined)
    if operation == "removeImageRefs":
        return re.sub(
            r"!\[\]\(images\/[0-9a-fA-F]\.jpg\)|"
            r"[a-fA-F0-9]+\.[a-zA-Z]{3,4}\)|"
            r"!\[\]\(images\/[a-f0-9]|"
            r"图\s+\d+-\d+：[\u4e00-\u9fa5a-zA-Z0-9]+|"
            r"(?:[0-9a-zA-Z]+){7,}|"
            r"(?:[一二三四五六七八九十零壹贰叁肆伍陆柒捌玖拾佰仟万亿]+){5,}|"
            r"u200e|"
            r"&#247;|\? :|"
            r"[�□]|\{\/U\}|"
            r"U\+26[0-F][0-D]|U\+273[3-4]|U\+1F[3-6][0-4][0-F]|"
            r"U\+1F6[8-F][0-F]",
            "",
            value,
        )
    raise AssertionError(operation)


def _apply_rule(
    normalized: dict[str, Any], field: str, rule: dict[str, Any]
) -> tuple[bool, int]:
    rule_type = rule.get("type")
    allowed = {
        "contentNull": {"type", "outputKey"},
        "wordNumber": {"type", "min", "max", "outputKey"},
        "sentenceNumber": {"type", "min", "max", "outputKey"},
        "charNumber": {"type", "threshold", "outputKey"},
        "uniqueWords": {"type", "threshold", "outputKey"},
        "colonEnd": {"type", "outputKey"},
        "lineEndWithEllipsis": {"type", "threshold", "outputKey"},
        "symbolWordRatio": {"type", "threshold", "outputKey"},
        "alphaWords": {"type", "threshold", "useTokenizer", "outputKey"},
        "htmlEntity": {"type", "outputKey"},
        "idCard": {"type", "threshold", "outputKey"},
        "noPunc": {"type", "threshold", "outputKey"},
        "specialCharacter": {"type", "outputKey"},
        "watermark": {"type", "watermarks", "outputKey"},
        "meanWordLength": {"type", "minLength", "maxLength", "outputKey"},
        "stopWord": {"type", "threshold", "useTokenizer", "outputKey"},
        "curlyBracket": {"type", "threshold", "outputKey"},
        "capitalWords": {"type", "threshold", "useTokenizer", "outputKey"},
        "loremIpsum": {"type", "threshold", "outputKey"},
        "lineStartWithBulletpoint": {"type", "threshold", "outputKey"},
        "lineWithJavascript": {"type", "threshold", "outputKey"},
        "blocklist": {
            "type",
            "language",
            "threshold",
            "useTokenizer",
            "outputKey",
        },
    }
    if rule_type not in allowed:
        _unsupported("text.rule-filter rule type is unsupported")
    _only_keys(rule, allowed[rule_type], f"text.rule-filter {rule_type}")
    text = normalized.get(field)
    if rule_type == "contentNull":
        return bool(text is not None and text.strip() != ""), 1
    if not text:
        return False, 0
    if rule_type == "wordNumber":
        count = len(tuple(text.split()))
        return (
            _integer(rule.get("min", 20), "min")
            <= count
            < _integer(rule.get("max", 100000), "max")
        ), count
    if rule_type == "sentenceNumber":
        count = len(re.findall(r"\b[^.!?\n]+[.!?]*", text, flags=re.UNICODE))
        return (
            _integer(rule.get("min", 3), "min")
            <= count
            <= _integer(rule.get("max", 7500), "max")
        ), 1
    if rule_type == "charNumber":
        count = len(text.strip().replace(" ", "").replace("\n", "").replace("\t", ""))
        return count >= _integer(rule.get("threshold", 100), "threshold"), 1
    if rule_type == "uniqueWords":
        words = tuple(text.lower().split())
        ratio = len(set(words)) / len(words) if words else 0.0
        return ratio > _number(rule.get("threshold", 0.1), "threshold"), 1
    if rule_type == "colonEnd":
        return not text.endswith(":"), 1
    if rule_type == "lineEndWithEllipsis":
        paragraphs = _paragraphs(text)
        if not paragraphs:
            return False, 1
        occurrences = sum(
            paragraph.rstrip().endswith(("...", "…")) for paragraph in paragraphs
        )
        ratio = occurrences / len(paragraphs)
        return ratio < _number(rule.get("threshold", 0.3), "threshold"), 1
    if rule_type == "symbolWordRatio":
        tokens = re.findall(r"\w+|[^\w\s]+", text, flags=re.UNICODE)
        if not tokens:
            return False, 1
        num_symbols = float(sum(text.count(symbol) for symbol in ("#", "...", "…")))
        return (
            num_symbols / len(tokens)
            < _number(rule.get("threshold", 0.4), "threshold")
        ), 1
    if rule_type == "alphaWords":
        words = _tokenize(text, _boolean(rule.get("useTokenizer"), "useTokenizer"))
        if not words:
            return False, 1
        ratio = sum(bool(re.search(r"[a-zA-Z]", word)) for word in words) / len(
            words
        )
        return ratio > _number(rule.get("threshold"), "threshold"), 1
    if rule_type == "htmlEntity":
        patterns = (
            pattern
            for entity in _DEFAULT_HTML_ENTITIES
            for pattern in (
                f"&{entity}；",
                f"&{entity};",
                f"＆{entity}；",
                f"＆{entity};",
                f"＆{entity}",
                f"&{entity}",
            )
        )
        return not any(pattern in text for pattern in patterns), 1
    if rule_type == "idCard":
        pattern = (
            r"(身\s{0,10}份|id\s{0,10}number\s{0,10}|identification|identity|"
            r"\s{0,10}ID\s{0,10}No\s{0,10}|id\s{0,10}card\s{0,10}|"
            r"NRIC\s{0,10}number\s{0,10}|IC\s{0,10}number\s{0,10}|"
            r"resident\s{0,10}registration\s{0,10}|"
            r"I.D.\s{0,10}Number\s{0,10})"
        )
        return len(re.findall(pattern, text, re.IGNORECASE)) < _integer(
            rule.get("threshold", 3), "threshold"
        ), 1
    if rule_type == "noPunc":
        paragraphs = tuple(line for line in text.split("\n") if line.strip())
        longest = max(
            len(sentence.split())
            for paragraph in paragraphs
            for sentence in re.split(r"[–.!?,;•/|…]", paragraph)
        ) if paragraphs else 0
        return longest <= _integer(rule.get("threshold", 112), "threshold"), 1
    if rule_type == "specialCharacter":
        patterns = (
            r"u200e",
            r"&#247;|\? :",
            r"[�□]|\{\/U\}",
            r"U\+26[0-F][0-D]|U\+273[3-4]|U\+1F[3-6][0-4][0-F]|"
            r"U\+1F6[8-F][0-F]",
        )
        return not any(re.search(pattern, text) for pattern in patterns), 1
    if rule_type == "watermark":
        watermarks = _string_list(
            rule.get("watermarks", ["Copyright", "Watermark", "Confidential"]),
            "watermarks",
        )
        return re.search("|".join(watermarks), text) is None, 1
    if rule_type == "meanWordLength":
        words = text.split()
        if not words:
            return False, 1
        mean_length = round(sum(map(len, words)) / len(words), 2)
        return (
            _number(rule.get("minLength", 3), "minLength")
            <= mean_length
            < _number(rule.get("maxLength", 10), "maxLength")
        ), 1
    if rule_type == "stopWord":
        words = _tokenize(
            text.lower(), _boolean(rule.get("useTokenizer"), "useTokenizer")
        )
        count = sum(word in _stopwords() for word in words)
        ratio = count / len(words) if words else 0
        return (
            ratio > _number(rule.get("threshold"), "threshold")
            and count > 2
        ), 1
    if rule_type == "curlyBracket":
        ratio = (text.count("{") + text.count("}")) / len(text)
        return ratio < _number(rule.get("threshold", 0.025), "threshold"), 1
    if rule_type == "capitalWords":
        words = _tokenize(
            text, _boolean(rule.get("useTokenizer", False), "useTokenizer")
        )
        ratio = sum(map(str.isupper, words)) / len(words) if words else 0
        return ratio <= _number(rule.get("threshold", 0.2), "threshold"), 1
    if rule_type == "loremIpsum":
        ratio = len(re.findall("lorem ipsum", text, re.IGNORECASE)) / len(
            text.lower()
        )
        return ratio <= _number(rule.get("threshold", 3e-8), "threshold"), 1
    if rule_type == "lineStartWithBulletpoint":
        paragraphs = _paragraphs(text)
        bullets = ("•", "‣", "▶", "◀", "◦", "■", "□", "▪", "▫", "–")
        ratio = sum(line.lstrip().startswith(bullets) for line in paragraphs) / len(
            paragraphs
        )
        return ratio <= _number(rule.get("threshold", 0.9), "threshold"), 1
    if rule_type == "lineWithJavascript":
        paragraphs = _paragraphs(text, normalize=True)
        occurrences = sum("javascript" in line for line in paragraphs)
        not_javascript = len(paragraphs) - occurrences
        return (
            len(paragraphs) <= 3
            or not_javascript >= _integer(rule.get("threshold", 3), "threshold")
        ), 1
    if rule_type == "blocklist":
        words = _tokenize(
            text.lower(), _boolean(rule.get("useTokenizer", False), "useTokenizer")
        )
        count = sum(word in _blocklist(rule.get("language", "en")) for word in words)
        return count <= _integer(rule.get("threshold", 1), "threshold"), 1
    raise AssertionError(rule_type)


def _invocation(
    operator_id: str, kind: str, config: dict[str, Any], source_id: str
) -> DataFlowInvocation:
    return DataFlowInvocation(
        operator_id=operator_id,
        pack_id=COMPAT_PACK_ID,
        pack_version=COMPAT_PACK_VERSION,
        kind=kind,
        config=copy.deepcopy(config),
        source_id=source_id,
    )


def _paragraphs(text: str, *, normalize: bool = False) -> tuple[str, ...]:
    paragraphs = tuple(
        match
        for match in re.findall(r"([^\n]*\n|[^\n]+$)", text)
        if match.strip()
    )
    if not normalize:
        return paragraphs
    return tuple(_normalize_rule_line(paragraph) for paragraph in paragraphs)


def _normalize_rule_line(value: str) -> str:
    punctuation = string.punctuation.replace("_", "")
    value = value.translate(str.maketrans("", "", punctuation))
    value = re.sub(r"\s+", " ", value.lower().strip())
    return unicodedata.normalize("NFD", value)


def _tokenize(text: str, use_tokenizer: bool) -> tuple[str, ...]:
    if not use_tokenizer:
        return tuple(text.split())
    try:
        from nltk.tokenize import word_tokenize

        return tuple(word_tokenize(text))
    except (ImportError, LookupError):
        _unsupported("NLTK word tokenizer data is unavailable in this installation")


@cache
def _decoded_asset(sha256: str, encoded: str) -> frozenset[str]:
    raw = zlib.decompress(base64.b64decode(encoded))
    if hashlib.sha256(raw).hexdigest() != sha256:
        _unsupported("embedded compatibility asset failed its SHA-256 check")
    return frozenset(line.strip().lower() for line in raw.decode().splitlines() if line)


def _stopwords() -> frozenset[str]:
    return _decoded_asset(*_NLTK_STOPWORDS_ASSET)


def _blocklist(language: Any) -> frozenset[str]:
    if not isinstance(language, str) or language not in _BLOCKLIST_ASSETS:
        _unsupported("Blocklist language must be en or zh")
    return _decoded_asset(*_BLOCKLIST_ASSETS[language])


def _normalized(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("normalizedData")
    if not isinstance(value, dict):
        value = {}
        item["normalizedData"] = value
    return value


def _record_rejection(rejected: list[str], item: dict[str, Any]) -> None:
    candidate_id = item.get("candidateId")
    if isinstance(candidate_id, str):
        rejected.append(candidate_id)
    elif candidate_id is not None:
        rejected.append(str(candidate_id))


def _rule_output_key(rule: dict[str, Any]) -> str:
    return _config_string(rule, "outputKey", "filter_label")


def _validate_items(items: object) -> None:
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        _unsupported("items must be a list of candidate objects")


def _mapping(value: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _unsupported(f"{name} must be an object")
    return copy.deepcopy(dict(value))


def _only_keys(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        _unsupported(f"{name} config key is unsupported: {unknown[0]}")


def _required_string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        _unsupported(f"{key} must be a non-empty string")
    return result


def _optional_string(value: Mapping[str, Any], key: str, default: str) -> str:
    result = value.get(key, default)
    if not isinstance(result, str) or not result:
        _unsupported(f"{key} must be a non-empty string")
    return result


def _config_string(value: Mapping[str, Any], key: str, default: str) -> str:
    return _optional_string(value, key, default)


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        _unsupported(f"{name} must be a list of non-empty strings")
    return list(value)


def _string_field(normalized: Mapping[str, Any], field: str) -> str:
    value = normalized.get(field)
    return value if isinstance(value, str) else ""


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _unsupported(f"{name} must be an integer")
    return value


def _number(value: Any, name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        _unsupported(f"{name} must be a number")
    return float(value)


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _unsupported(f"{name} must be a boolean")
    return value


def _unsupported(reason: str) -> Any:
    raise ValueError(f"dataflow_operator_unsupported: {reason}")


__all__ = [
    "COMPAT_EXECUTORS",
    "COMPAT_OPERATOR_DEFINITIONS",
    "COMPAT_PACK_ID",
    "COMPAT_PACK_VERSION",
    "DATAFLOW_ALIAS_SOURCE_IDS",
    "DATAFLOW_COMPAT_SHA",
    "DataFlowInvocation",
    "translate_dataflow_alias",
]
