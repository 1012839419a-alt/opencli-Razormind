---
title: 'GitHub #33: Govern ResearchGraph V2 Evidence Review and Pinned Fold'
type: 'feature'
created: '2026-08-30'
baseline_commit: 'c44f735b3121827b1b9069444189c1eb73e16fb4'
status: 'done'
review_loop_iteration: 0
context:
  - 'CONTEXT.md'
  - 'docs/wayfinder/iii-vertical/define-researchgraph-delivery-authority.md'
  - '_bmad-output/implementation-artifacts/spec-gh-32-evidence-batch-materialization.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #32 has immutable EvidenceBatch manifest revisions, but ResearchGraph V1 permits unauthenticated, shape-only mutations and provenance that does not prove terminal manifest finality. Operators therefore cannot review eligible research evidence or pin a graph fold without allowing stale, amended, partial, or bypassed facts to impersonate authority.

**Approach:** Add a versioned, append-only `AuthorizedResearchGraphEventV2` overlay to the existing WorkflowRunEvent transcript. It accepts only scoped, actor-authorized mutations and final #32 manifest tuples, folds a pinned reviewable graph projection deterministically, and exposes redacted scoped Studio status/recovery. It remains a non-authoritative graph; #34 alone owns Delivery authorization.

## Boundaries & Constraints

**Always:** Preserve V1 envelopes, V1 deterministic replay, graph IDs, and `research.publish-gate`/continuation behavior byte-for-byte. V2 events retain schema/policy version, run/node/batch/manifest derivation/reconciliation revision/hash lineage, immutable mutation identity/idempotency binding, actor/principal/capability/authorization evidence, expected sequence/revision, and resulting revision/fold identity. Resolve an evidence reference only through Admin's scoped #32 materialization projection; `odpRef` is display provenance and never resolves. Accept only `completed`, `completed_empty`, or `partial` manifests whose immutable tuple matches current scoped materialization facts. `completed_empty` contributes no lineage; `partial` contributes only explicit `record_present` refs after the candidate revision explicitly excludes every rejected/DLQ item and every delivered claim has complete present refs. Pin one exact fold sequence/revision/manifest-set hash for downstream inspection. Any later compatible #32 revision appends an explicit superseding graph event and review state; it never mutates historical events or an existing pin.

**Ask First:** Changing #29–#32 identities, manifest precedence/signature/redaction policy, V1 publish-gate semantics, the WorkflowRunEvent allocator, workspace RBAC policy definitions, or adding Delivery/receiver/ODP/collector paths.

**Never:** Admit `indeterminate`, unknown, stale, scope/hash-mismatched, missing, failed-definitive, legacy/unmaterialized, URI-only, or nonterminal batches; infer evidence from pages, counts, `odpRef`, or ODP identifiers; create a graph fact table/cache authority; accept client actor/capability strings; silently update a pinned fold; let a graph boolean authorize Delivery; expose raw ODP data, signatures, rejection details, or cross-scope graph state.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Eligible completed batch | Scoped current `completed` manifest tuple; complete record-present claim refs | Authorized contributor appends V2 lineage and a reviewable fold/pin | Tuple, scope, hash, or lineage mismatch appends nothing |
| Successful zero | Valid `completed_empty` manifest | Append auditable V2 context only; create no source/evidence/claim | Never infer evidence from zero/counts |
| Partial candidate | Terminal `partial`; explicit rejected/DLQ exclusion and all delivered refs present | Append only permitted record-present lineage | Missing exclusion or any incomplete claim blocks the candidate |
| Human review | Scoped proposer then scoped verifier under independent-review policy | Persist capability/principal/policy evidence; verified state is fold-eligible | Self-review, missing capability, duplicate/changed idempotency authority, or unauthorized actor is rejected |
| CAS/replay | Matching current sequence/revision and same canonical mutation plus authorization binding | Append one event and return exact replay | Stale/mismatched CAS or changed replay appends nothing |
| Late amendment | Later #32 reconciliation revision changes a referenced manifest | Append V2 supersession/review-block event retaining old pin/history | Never silently refold/revise the prior event |
| Pinned inspection | Scoped Studio request names an exact fold/revision | Return bounded redacted status, pin lineage, blocker, and safe recovery | Fold/manifest mismatch blocks use and names re-review; cross-scope/raw fields are rejected |

</frozen-after-approval>

## Code Map

- `backend/models/workflow_run.py:46-77` and `backend/workflow/workflow_run_events.py:49-166` -- unchanged sole durable append history, locked run allocator, canonical replay/idempotency, and transaction boundary.
- `backend/schemas/research_graph_v2.py` and `backend/workflow/research_graph_v2.py` -- V2-only immutable authorization/manifest/pin envelopes, pure fold, scoped #32 validation, and transactional append overlay; V1 files remain untouched.
- `backend/models/iii_collection.py` and `backend/security/{identity,workspace_rbac}.py` -- existing immutable manifest ledger and server-derived identity/capability seams; no ODP query or client authority.
- `backend/api/v1/research_graph_v2_routes.py` and `backend/api/v1/__init__.py` -- scoped authenticated Studio V2 routes and the sole new-router registration patch.
- `tests/unit/test_research_graph_v2.py` and `tests/integration/test_research_graph_v2_api.py` -- deterministic fold plus authenticated Studio/replay/CAS/partial/zero/supersession/pin smoke coverage.

## Tasks & Acceptance

**Execution:**
- [x] `backend/schemas/research_graph_v2.py` and `backend/workflow/research_graph_v2.py` -- define/fold V2 immutable authorization, manifest, supersession, review, pin, and policy contracts beside untouched untracked V1; enforce authorization-bound idempotency and transactional sequence+revision CAS.
- [x] `backend/workflow/research_graph_v2.py` -- resolve exact scoped #32 manifest revisions/record refs without ODP access; persist all V2 facts solely as append-only WorkflowRunEvents.
- [x] `backend/api/v1/research_graph_v2_routes.py` and `backend/api/v1/__init__.py` -- require per-route existing workspace RBAC/capabilities, reject self-review, record independent actor evidence, return bounded redacted review/status/recovery, and register only V2.
- [x] `tests/unit/test_research_graph_v2.py` and `tests/integration/test_research_graph_v2_api.py` -- TDD replay/conflict, late supersession, pin mismatch, zero/partial rules, authenticated scope/redaction, and no-Delivery/no-ODP bypass.

**Acceptance Criteria:**
- Given a fresh scoped terminal #32 manifest, when a V2 contributor proposes eligible lineage, then Admin stores complete immutable manifest/run/node/batch/revision/hash and policy/actor lineage through the shared event transaction only.
- Given a verify/reject/retract action, when its route evaluates a scoped capability, then only the permitted independent authenticated actor appends it; self-approval or client-supplied authority cannot advance sequence or review state.
- Given stale expected sequence/revision, changed replay content or authorization, retraction, bad scope/hash, or blocked materialization state, when submitted, then the graph history and pin remain unchanged and a fail-closed conflict is returned.
- Given `partial`, `completed_empty`, or later manifest amendment, when folded, then partial claims need explicit exclusions and complete present refs, zero contributes no evidence, and amendment appends explicit supersession/re-review rather than mutating the old fold.
- Given a pinned fold is read or referenced, when any pinned sequence/revision/manifest set disagrees with the current authorized candidate, then it is blocked; V1 content publish-gate results remain unchanged and advisory.

## Spec Change Log
- 2026-08-30: Reopened after source audit. Require complete record-reference equality, read-time immutable-manifest freshness overlays, replay capability/pin validation, and auditable completed-empty context events.

## Design Notes

V2 is an overlay because the existing event transcript is the only ordering and durability authority. The pinned fold is a deterministic read-model identity, not a Delivery decision or a permission grant; a later manifest amendment can supersede only through a new authorized event.

## Verification

**Commands:**
- `uv run --extra dev pytest --no-cov tests/unit/test_research_graph_v2.py tests/integration/test_research_graph_v2_api.py` -- expected: TDD contracts cover eligible/zero/partial, authenticated authorization, replay/CAS, supersession, pins, scoped read/redaction, and no ODP/Delivery bypass.
- `uv run --extra dev pytest --no-cov tests/integration/test_workflow_deep_research_api.py` and the shared-tree `tests/unit/test_research_graph.py` regression -- expected: existing content publish-gate and untouched V1 graph behavior remain unchanged and advisory.
- actual authenticated Studio API smoke against the local test application -- expected: scoped redacted review/status/recovery succeeds, cross-scope/self-review/bypass calls fail closed, and no raw ODP fields appear.
- Sentrux session start/end for the touched backend scope and independent code review -- expected: no structural or authority-boundary regression.

## Suggested Review Order

**Scoped authority boundary**

- Authenticate and authorize before resolving scoped Studio resources.
  [`research_graph_v2_routes.py:62`](../../backend/api/v1/research_graph_v2_routes.py#L62)

- Append only authorized, immutable V2 envelopes to the existing event transcript.
  [`research_graph_v2.py:428`](../../backend/workflow/research_graph_v2.py#L428)

**Deterministic evidence fold**

- Replay only valid V2 events while CAS follows every transcript event.
  [`research_graph_v2.py:98`](../../backend/workflow/research_graph_v2.py#L98)
- Validate final manifest tuples, terminality, and partial exclusions before authority advances.
  [`research_graph_v2.py:255`](../../backend/workflow/research_graph_v2.py#L255)

**Public contract and proof**

- Define redacted event lineage and mutation/read contracts.
  [`research_graph_v2.py:1`](../../backend/schemas/research_graph_v2.py#L1)

- Exercise authenticated Studio lifecycle, replay, pinning, supersession, and redaction.
  [`test_research_graph_v2_api.py:1`](../../tests/integration/test_research_graph_v2_api.py#L1)

- Defend independent review and transcript-tail CAS in pure replay.
  [`test_research_graph_v2.py:60`](../../tests/unit/test_research_graph_v2.py#L60)
