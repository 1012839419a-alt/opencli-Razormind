# DataFlow operator packs

OpenCLI Admin internalizes DataFlow as versioned workflow capabilities, not as
a copy of every upstream Python class. One native operator may cover a family
of upstream fine-grained operators when their runtime and port contracts are
the same.

Upstream baseline: `OpenDCAI/DataFlow@f62aa1349e0ff14cb737a4cbda1945d04fde85bb`.

## Runnable v1 scope

All v1 operators use `recordCandidate[] -> recordCandidate[]`, preserve source
lineage, do not mutate their input, and return metrics plus stable rejected
candidate IDs.

| Pack | Native operator | DataFlow capability family |
| --- | --- | --- |
| `builtin.core-data@1.0.0` | `core.generate.instruction-pairs` | deterministic instruction-pair shaping |
|  | `core.filter.quality` | basic quality gate |
|  | `core.evaluate.quality` | basic quality scoring |
|  | `core.refine.text` | basic text normalization |
| `builtin.text-cleaning@1.0.0` | `text.clean` | HTML/entity/URL/emoji/whitespace and configurable text cleanup |
|  | `text.rule-filter` | non-empty, length, ratio and blocklist rules |
|  | `text.deduplicate` | exact and SimHash duplicate removal (SimHash here is a native v1 capability; the pinned 1.1.0 DataFlow import contract maps only `HashDeduplicateFilter` and `NgramHashDeduplicateFilter`, not `SimHashDeduplicateFilter`) |
|  | `text.statistics` | character, word, sentence and lexical-diversity metrics |
| `builtin.dataset-preparation@1.0.0` | `data.project` | select, rename, coalesce and scalar cast |
|  | `data.chunk` | deterministic chunking with overlap |
|  | `data.qa-extract` | source-grounded existing QA-pair extraction |
|  | `data.training-format` | deterministic Alpaca/ShareGPT-style shaping |

`builtin.text-cleaning@1.1.0` is the pinned DataFlow compatibility profile.
It keeps the three deep native operators `text.clean`, `text.rule-filter`, and
`text.deduplicate`, while reproducing 34 SHA-locked upstream classes:

- `RemoveExtraSpacesRefiner`, `LowercaseRefiner`, `HtmlUrlRemoverRefiner`,
  `HtmlEntityRefiner`, `RemoveEmojiRefiner`, `RemoveNumberRefiner`,
  `RemovePunctuationRefiner`, and `RemoveRepetitionsPunctuationRefiner`;
- `ContentNullFilter`, `WordNumberFilter`, `SentenceNumberFilter`,
  `CharNumberFilter`, and `UniqueWordsFilter`;
- the remaining deterministic CPU rule filters, including colon/ellipsis,
  symbol and alpha ratios, HTML entity, ID-card, punctuation, watermark,
  word-length, stop-word, bracket, capitalization, Lorem Ipsum, bullet-point,
  and JavaScript-line checks;
- `TextNormalizationRefiner`, `RemoveImageRefsRefiner`, and `BlocklistFilter`;
- `HashDeduplicateFilter` and `NgramHashDeduplicateFilter` (`md5`/`sha256`).

DataFlow import identities use the complete form
`dataflow@<sha>::dataflow.operators.<module>.<Class>`. Short or unversioned
aliases are rejected. Imported workflows persist the native `operatorId`,
`packVersion`, translated config, and safe upstream provenance. The runtime
never imports DataFlow or pandas.

The Canvas keeps four execution primitives (`generate`, `filter`, `evaluate`,
`refine`) and selects an operator from the backend capability manifest. This
keeps the node catalog usable while retaining a versioned, queryable operator
identity in every compiled workflow.

## Resource-dependent packs

The following DataFlow families are inventoried but are not declared runnable
until their real resource adapter exists:

- prompted generation/refinement/evaluation, multi-hop QA, reasoning and
  Text2SQL: model-provider adapter;
- embedding, retrieval, reranking and vector index writes: embedding/vector
  resource contracts;
- PDF/URL-to-Markdown and MinerU transforms: document conversion adapter;
- OCR, speech and vision operators: modality-specific runtime adapters;
- Perspective, Presidio, LangKit and heavyweight semantic evaluators: explicit
  dependency/service adapters.

These capabilities must fail closed as unavailable. A deterministic placeholder
must never be reported as RAG synthesis, OCR, embedding, or semantic evaluation.

## Acceptance contract

Each runnable operator must pass:

1. direct happy-path, empty-batch, invalid-config, determinism and input
   immutability checks;
2. compile-time rejection of missing, unknown, or kind-mismatched `operatorId`;
   explicit unsupported pack versions and unpinned DataFlow aliases also fail
   closed;
3. runtime events carrying pack/version, lineage, metrics and bounded rejected
   IDs without raw source bodies;
4. an end-to-end workflow from fixture source through normalize, preparation,
   cleaning, acceptance and record sink;
5. demand-draft projection and Canvas selection without hand-editing the graph.

Pinned compatibility additionally locks upstream source digests and golden
outputs under `tests/fixtures/dataflow/`. A dependency-capable job may run the
isolated upstream oracle; normal project tests validate the same golden
contract without adding DataFlow to application dependencies.
