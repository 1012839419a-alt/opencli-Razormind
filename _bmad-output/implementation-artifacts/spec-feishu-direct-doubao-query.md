---
title: 'Send Feishu terms directly to Doubao and preserve complete research output'
type: 'bugfix'
created: '2026-08-28'
status: 'done'
baseline_commit: '735d71caec4e28cf5d6953248ec51efa211316dd'
review_loop_iteration: 0
context:
  - 'D:/projects/opencli-Razormind/CONTEXT.md'
  - 'D:/projects/opencli-Razormind/docs/workflow-node-capability-mapping.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The current Feishu-to-Doubao workflow transforms the Feishu recommendation into a template prompt and routes it through the Douyin node first. This means Doubao is not asked the exact term supplied by the operator, and the stored result does not expose all useful answer data and links as one coherent record.

**Approach:** Make the Feishu row's configured keyword the direct Doubao question and remove the Douyin hop from this workflow path. Request a stable structured response from Doubao containing the original question, complete answer, data/details, links or citations, session-share data, and suggested keywords; preserve both parsed fields and the raw response through Records and the Data Workbench.

## Boundaries & Constraints

**Always:** Treat the Feishu keyword field as the authoritative question, preserving its exact text and source row identity. Keep credentials in the existing source/connection boundary. Use the existing Doubao OpenCLI channel and upstream interpolation. Preserve raw response, parsed answer, structured data, links/citations, share data, and suggested keywords without silently dropping unknown fields. Keep bounded execution and existing deduplication/lineage behavior.

**Ask First:** Whether future runs should also write the normalized result back to Feishu; this change remains read-only for Feishu and stores authoritative results in Records/Data Workbench.

**Never:** Do not prepend a business-specific prompt template to the Feishu question, do not use Douyin output as the Doubao question, do not fabricate links or answer data, and do not bypass the governed OpenCLI/session boundary.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | Feishu row contains a non-empty recommendation | Doubao receives that exact text; one record preserves answer, data, links, share data, suggestions, raw response, and row lineage | N/A |
| STRUCTURED_ALIAS | Doubao uses alternate names such as `data`, `details`, `links`, `references`, or `suggested_keys` | Equivalent canonical fields are populated without losing raw response | Keep unknown fields in raw response |
| EMPTY_ROW | Feishu row has blank keyword | Row is skipped and no empty Doubao request is emitted | Existing row validation/reporting applies |
| UNAVAILABLE | Doubao/OpenCLI session is unavailable | No fabricated Record is created | Return the existing structured channel failure |

</frozen-after-approval>

## Code Map

- `frontend/lib/workflow/studio-templates.ts` -- current `feishuDouyinDoubaoGraph`; remove the Douyin hop, set the Doubao question to the upstream keyword directly, and update the template description/adapter list.
- `backend/workflow/channel_source_executor.py` -- `_interpolate` and source dispatch; preserve exact upstream `keyword` semantics when invoking Doubao.
- `backend/channels/doubao_research_channel.py` -- `_structured_response` and `DoubaoResearchChannel.collect`; parse canonical answer/data/link/share/suggestion fields and emit them in one item.
- `backend/pipeline/normalizer.py` and `backend/models/record.py` -- standard fields plus `extra_*` carry-through and durable raw/normalized storage; no secrets belong in either payload.
- `tests/unit/workflow/test_channel_source_executor.py` -- direct keyword interpolation and one-request-per-Feishu-row regression coverage.
- `tests/unit/channels/test_doubao_research_channel.py` -- structured output, URL extraction, aliases, and raw-result preservation coverage.
- `tests/frontend` or the existing frontend workflow contract checks -- verify the generated graph is Feishu → Doubao → hygiene → Records.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/lib/workflow/studio-templates.ts` -- change the template graph to pass Feishu keywords directly to Doubao and remove the unused Douyin route -- prevents the wrong query source.
- [x] `backend/channels/doubao_research_channel.py` -- normalize answer, data, links, citations, share data, and suggested keywords while retaining raw output -- preserves complete research evidence.
- [x] `tests/unit/channels/test_doubao_research_channel.py` and `tests/unit/workflow/test_channel_source_executor.py` -- add direct-question and complete-output regression tests -- prevents recurrence.

**Acceptance Criteria:**
- Given two Feishu rows with recommendation text, when the workflow executes, then Doubao receives each exact recommendation text as its question, with no template prefix and no Douyin-derived substitution.
- Given a valid Doubao response containing an answer, data, links or citations, share information, and suggestions, when the item is normalized and stored, then the Data Workbench exposes those fields together with the original Feishu row lineage and raw response.
- Given an empty or unavailable input, when execution runs, then no empty/fabricated research record is stored and the existing structured error behavior remains intact.

## Verification

**Commands:**
- `$env:TASK_EXECUTOR='local'; uv run --with pytest --with pytest-asyncio pytest -o addopts='' tests/unit/channels/test_doubao_research_channel.py tests/unit/channels/test_feishu_table_channel.py tests/unit/workflow/test_channel_source_executor.py -q` -- expected: all selected tests pass.
- `npm --prefix frontend run check:workflow-regressions` -- expected: workflow graph and node contracts pass.
- `git diff --check` -- expected: no whitespace errors.

## Suggested Review Order

**Direct query boundary**

- The channel forwards the resolved question without adding a business prompt.
  [`doubao_research_channel.py:164`](../../backend/channels/doubao_research_channel.py#L164)

- The executor interpolates each Feishu keyword into one direct Doubao request.
  [`test_channel_source_executor.py:8`](../../tests/unit/workflow/test_channel_source_executor.py#L8)

**Complete result preservation**

- Parsed aliases become canonical data and links while the full response remains available.
  [`doubao_research_channel.py:41`](../../backend/channels/doubao_research_channel.py#L41)

- The emitted item carries answer, data, links, citations, sharing, suggestions, and raw output.
  [`doubao_research_channel.py:200`](../../backend/channels/doubao_research_channel.py#L200)

**Workflow topology**

- The template removes Douyin and connects Feishu directly to Doubao.
  [`studio-templates.ts:139`](../../frontend/lib/workflow/studio-templates.ts#L139)

- Regression tests pin the complete structured-output contract and aliases.
  [`test_doubao_research_channel.py:32`](../../tests/unit/channels/test_doubao_research_channel.py#L32)
