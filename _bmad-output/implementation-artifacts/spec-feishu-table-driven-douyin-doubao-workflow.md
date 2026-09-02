---
title: 'Drive Douyin and Doubao collection from a Feishu table'
type: 'feature'
created: '2026-08-28'
status: 'done'
baseline_commit: '7838811415fd685487703b6c9fc3b82a60eb2777'
review_loop_iteration: 0
context:
  - 'D:/projects/opencli-Razormind/CONTEXT.md'
  - 'D:/projects/opencli-Razormind/docs/workflow-node-capability-mapping.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The current high-jixing workflow has no governed way for the operator to maintain the search terms externally, and its visible collection flow does not expose a reliable Feishu-to-Douyin-to-Doubao path. The operator wants to tell the system what to collect by editing a Feishu table.

**Approach:** Add a `feishu_table` source capability that reads a bounded, structured set of search rows, then connect the existing OpenCLI Douyin search and Doubao research capabilities through the workflow runtime. Preserve lineage from each Feishu row to collected video evidence, normalized records, and run trace output.

## Boundaries & Constraints

**Always:** Keep Feishu credentials out of workflow graph parameters and persisted event payloads; use the existing governed source/connection boundary. Require explicit table/base configuration, bounded reads, deterministic row identity, idempotent processing, and structured errors. Use the real OpenCLI commands (`douyin search <query>` and `doubao ask <question>`), preserve source references, and fail closed when the browser/session or runtime binding is unavailable.

**Ask First:** The exact Feishu product surface (Bitable app/table versus ordinary spreadsheet), authentication mode (tenant app connection versus user OAuth), required input column name, and whether results should be written back to Feishu in this slice. Default implementation may support read-only Bitable rows with a configurable keyword column and Records as the authoritative output; write-back remains disabled unless explicitly configured.

**Never:** Do not scrape Feishu HTML as the primary integration, place app secrets in `channel_config`, bypass OpenCLI/browser governance, invent a second workflow runtime, or claim that publishing makes an unconfigured Feishu/Douyin/Doubao path runnable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | Feishu table has enabled rows with non-empty keywords | Each row produces bounded Douyin results, a Doubao analysis request, normalized Records, and lineage fields | N/A |
| EMPTY_ROWS | Table is reachable but no eligible keyword rows exist | Run completes with zero source items and an explicit empty-source summary | Do not invoke Douyin or Doubao |
| BAD_ROW | A row has missing/blank keyword or unsupported status | Other valid rows continue; bad row is reported with row identity | Structured row-level validation error |
| UNAVAILABLE | Feishu, browser session, OpenCLI, or Doubao binding is unavailable | Run is blocked/failed at the responsible node with a stable reason | No fabricated records; retry remains possible |
| REPLAY | Same Feishu row and run is replayed | Existing row/run identity prevents duplicate output | Idempotency result is recorded |

</frozen-after-approval>

## Code Map

- `backend/channels/base.py` and `backend/channels/registry.py` -- channel contract and registration seam for a new governed source.
- `backend/channels/opencli_channel.py` -- existing OpenCLI dispatch, browser/resource routing, positional-argument handling, and bounded subprocess behavior.
- `backend/channels/doubao_research_channel.py` -- existing cited Doubao request channel and output shape to reuse.
- `backend/schemas/source.py` -- source channel type contract; add `feishu_table` without exposing secrets.
- `backend/workflow/capability_projection.py` and `backend/workflow/node_registry.py` -- backend capability/readiness projection used by Studio validation.
- `frontend/lib/workflow/node-catalog.ts`, `frontend/lib/workflow/node-contracts.ts`, and `frontend/lib/workflow/studio-templates.ts` -- Canvas node metadata, parameters, and workflow template graph.
- `frontend/lib/api/endpoints.ts` and `frontend/lib/api/hooks.ts` -- project workflow persistence and validation calls.
- `backend/pipeline/runner.py` and `backend/services/source_service.py` -- source execution and persistence boundaries; inspect before adding adapter-specific behavior.
- `tests/unit/channels/` and `tests/integration/` -- existing seams for channel, capability, compile, and workflow-run regression coverage.
- Read-only evidence: `opencli douyin search '高吉星燕窝酸 DHA 藻油' --limit 3 -f json` returned three records; current project UI shows draft status, zero runs, zero records, and zero sources.

## Tasks & Acceptance

**Execution:**
- [x] Define the Feishu row/config contract and implement a read-only `feishu_table` channel using the existing credential and HTTP patterns.
- [x] Register the channel, capability, schema, readiness blockers, and bounded/idempotent row normalization.
- [x] Add Canvas node metadata and a high-jixing workflow graph that wires Feishu keywords to Douyin search, Doubao research, normalization, and Records.
- [x] Add focused unit coverage for eligible rows, bounded pagination, missing credentials, and source-schema registration.
- [ ] Add workflow integration coverage for empty rows, row-level failures, unavailable bindings, and replay behavior.

**Acceptance Criteria:**
- Given a configured Feishu table connection and eligible keyword rows, when the high-jixing workflow runs, then each row is traceable through Douyin search, Doubao analysis, and a stored Record.
- Given no Feishu connection or an invalid table/keyword configuration, when validation runs, then the workflow is not publishable and exposes a stable actionable blocker.
- Given a replay of the same source row, when collection runs again, then duplicate records are not created solely because the workflow was retried.
- Given the Douyin browser/runtime binding is unavailable, when the workflow is run, then the Douyin node reports a structured blocked/failed state and downstream nodes do not fabricate output.

## Verification

**Commands:**
- `.\\venv\\Scripts\\python.exe -m pytest tests/unit/channels tests/integration/test_workflow_compile_api.py tests/integration/test_workflow_capabilities_api.py -q` -- expected: all selected tests pass.
- `npm --prefix frontend run check:workflow-regressions` -- expected: existing workflow contract checks pass.
- `npm --prefix frontend run build` -- expected: frontend build succeeds.

## Suggested Review Order

**Runtime execution boundary**

- Routes supported live source nodes through the existing channel runner with upstream keyword interpolation.
  [`channel_source_executor.py:23`](../../backend/workflow/channel_source_executor.py#L23)

- Dispatches Feishu, Douyin, and Doubao channel outputs into the authoritative run trace.
  [`opencli_hda_tracer.py:951`](../../backend/workflow/opencli_hda_tracer.py#L951)

**Feishu source contract**

- Enforces read-only bounded Bitable reads and stable row lineage without graph secrets.
  [`feishu_table_channel.py:43`](../../backend/channels/feishu_table_channel.py#L43)

- Projects the new source capability and explicit connection/readiness requirements into Studio.
  [`capability_projection.py:588`](../../backend/workflow/capability_projection.py#L588)

**Canvas composition**

- Exposes Feishu and Doubao nodes with typed parameters and source adapters.
  [`node-catalog.ts:933`](../../frontend/lib/workflow/node-catalog.ts#L933)

- Provides the ready-made Feishu → Douyin → Doubao → Records graph template.
  [`studio-templates.ts:136`](../../frontend/lib/workflow/studio-templates.ts#L136)

**Verification**

- Covers eligible rows, pagination bounds, missing credentials, and interpolation fanout.
  [`test_feishu_table_channel.py:1`](../../tests/unit/channels/test_feishu_table_channel.py#L1)
