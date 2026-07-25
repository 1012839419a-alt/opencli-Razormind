# DataFlow compatibility matrix

Baseline: `OpenDCAI/DataFlow@f62aa1349e0ff14cb737a4cbda1945d04fde85bb`.

OpenCLI Admin preserves DataFlow source identity at import time and compiles it
to a versioned native Data Operator invocation. The compatibility unit is an
upstream class plus its pinned source SHA, not an unversioned class name.

## Runnable exact compatibility

`builtin.text-cleaning@1.1.0` currently provides exact, dependency-free
compatibility for 34 upstream classes behind three native operators.

| Native operator | Pinned DataFlow classes |
| --- | --- |
| `text.clean` | `RemoveExtraSpacesRefiner`, `LowercaseRefiner`, `HtmlUrlRemoverRefiner`, `HtmlEntityRefiner`, `RemoveEmojiRefiner`, `RemoveNumberRefiner`, `RemovePunctuationRefiner`, `RemoveRepetitionsPunctuationRefiner`, `TextNormalizationRefiner`, `RemoveImageRefsRefiner` |
| `text.rule-filter` | `ContentNullFilter`, `WordNumberFilter`, `SentenceNumberFilter`, `CharNumberFilter`, `UniqueWordsFilter`, `ColonEndFilter`, `LineEndWithEllipsisFilter`, `SymbolWordRatioFilter`, `AlphaWordsFilter`, `HtmlEntityFilter`, `IDCardFilter`, `NoPuncFilter`, `SpecialCharacterFilter`, `WatermarkFilter`, `MeanWordLengthFilter`, `StopWordFilter`, `CurlyBracketFilter`, `CapitalWordsFilter`, `LoremIpsumFilter`, `LineStartWithBulletpointFilter`, `LineWithJavascriptFilter`, `BlocklistFilter` |
| `text.deduplicate` | `HashDeduplicateFilter`, `NgramHashDeduplicateFilter` |

The authoritative alias list and config translation live in
`backend/workflow/dataflow_compat.py`. Golden outputs and upstream source or
asset digests live in `tests/fixtures/dataflow/`.

## Inventoried but unavailable until their real dependency exists

| Family | Examples | Required adapter or asset |
| --- | --- | --- |
| Tokenizer or statistical text | `MinHashDeduplicateFilter`, `SimHashDeduplicateFilter`, `NgramFilter`, stop-word/stemming/lemmatization refiners | pinned tokenizer/library pack |
| Local language and quality models | `LanguageFilter`, `SemDeduplicateFilter`, Text-PT and Text-SFT quality filters | model artifact plus model digest |
| PII and entity processing | `NERRefiner`, `PIIAnonymizeRefiner`, `PresidioFilter` | NER/Presidio model adapter |
| Prompted cleaning and evaluation | `PromptedFilter`, `PromptedRefiner`, KBC text cleaner, model-judge filters | configured LLM provider |
| Document extraction | MinerU, PDF-to-Markdown, OCR and VQA extraction | document conversion or modality adapter |
| Retrieval and synthesis | embeddings, retrieval, reranking, multi-hop QA and RAG | embedding, vector-index and model adapters |
| Code and SQL execution | sandbox evaluators and SQL execution filters | isolated execution adapter |

Unavailable classes fail closed during DataFlow import. They are never mapped
to a merely similar deterministic implementation.

## Pipeline reproduction

The native import endpoint accepts `runtime: "dataflow"` with the pinned
`graph.sourceSha`. Each graph node supplies either the complete source identity
or `module + class`, plus constructor and run configuration. The importer
produces ordinary typed Workflow nodes with:

- canonical `operatorId`;
- exact `packVersion`;
- translated native config;
- safe DataFlow provenance.

Canvas still uses four reusable execution kinds: `generate`, `filter`,
`evaluate`, and `refine`. Imported upstream classes remain separately visible
as workflow nodes and provenance entries without creating 194 shallow runtime
implementations.
