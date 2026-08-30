---
title: 'GitHub #32: Materialize Scoped ODP EvidenceBatch and Studio State'
type: 'feature'
created: '2026-08-30'
status: 'done'
baseline_commit: 'aafc61774540b12635c88c600cd450e206fd60b3'
review_loop_iteration: 0
context:
  - 'CONTEXT.md'
  - 'docs/wayfinder/iii-vertical/define-odp-to-evidencebatch-materialization.md'
  - 'docs/wayfinder/iii-vertical/define-cross-plane-correlation-and-idempotency.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #29/#31 retain an immutable Admin attempt, final expected-key report, and signed ingress outcomes; #30 provides governed ODP reads. They intentionally stop before materialization, leaving operators unable to distinguish complete evidence from unknown data.

**Approach:** Add one Admin materializer joining durable attempt scope, one #31 report, signed outcomes, and #30 exact/frozen-page evidence. It appends immutable manifest/event revisions and returns a redacted scoped Studio/run state with recovery.

## Boundaries & Constraints

**Always:** ODP PostgreSQL is Record truth, reached only through `odp-query` using ledger-derived scope. Each V1 manifest retains reconciliation version, dispatch-task derivation, report/receipt/key-set/query/snapshot hashes, bounded refs/counts, status/revision, and manifest hash. Exact coverage plus retained facts reconciles; pages establish lineage only.

**Ask First:** Altering #29/#31 identity/signature policy, legacy `WorkflowRunStatus`, general/browser ODP predicates, definitive DLQ/retention semantics, or graph/delivery/receiver/ingress scope.

**Never:** Use Admin SQL, `/records`, notifications, 2xx, collector return, accepted/duplicate, no rows, page exhaustion/order/time, or `odpRef` as finality. Do not mutate history, leak raw ODP data/signatures/keys/payloads/reject details, or write new values to the legacy enum.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Nonempty completion | Final nonempty report; every key has non-rejected signed outcome and exact presence | Append `completed` with refs/query lineage | Accepted/duplicate is ingress only |
| Successful zero | Successful zero report; empty set; no contradiction | Append `completed_empty` with no refs | Empty page/absent receipt is not zero |
| Unknown/query/cursor | Missing fact, unknown retention/DLQ, outage, incomplete coverage, or invalid/racing cursor | `indeterminate`, legacy `blocked`, redacted re-reconcile action | No inferred finality |
| Reject/DLQ | Explicit retained rejection/DLQ; all other keys known | `partial`, or `failed_definitive` only with explicit retained collector facts meeting parent rule | Missing proof is `unknown` |
| Late fact/recovery | Compatible same-attempt fact or scoped recovery | Append revision; show mapped status, blocker, refs, recovery | Conflict is rejected/indeterminate |

</frozen-after-approval>

## Code Map

- `backend/models/iii_collection.py`, `backend/schemas/iii_collection.py`, and `backend/workflow/iii_collection_store.py:553-847` -- immutable #31 report/receipt, replay validation, and `await_reconciliation` seam.
- `backend/migrations/versions/a9b0c1d2e3f4_add_collector_ingress_receipts.py` -- append-only scoped fact-table convention.
- `backend/odp/query_client.py`, `backend/api/v1/odp_reconciliation.py`, `odp-rs/crates/odp-query/src/types.rs`, `odp-rs/crates/odp-query/src/query.rs`, and `odp-rs/crates/odp-query/src/main.rs` -- delegated exact/page API, `present`/`unknown`, fingerprint-bound frozen cursor, and failures.
- `backend/api/v1/iii_collections.py`, `backend/api/v1/studio_workflows.py`, `backend/models/workflow_run.py`, and `backend/schemas/workflow.py` -- scope guards, Studio presentation, and unchanged legacy status literal.
- `tests/integration/test_iii_collection_vertical.py`, `tests/unit/odp/test_query_client.py`, and `tests/integration/test_workflow_evidence_batches_api.py` -- signed-fact, zero/nonterminal, query/redaction, scope, and cursor fixtures.

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/iii_collection.py`, model registration, and new `backend/migrations/versions/*_add_evidence_batch_materialization.py` -- add immutable V1 manifests and append-only revisions keyed by scope, attempt, report/key-set, and query fingerprint.
- [x] `backend/schemas/iii_collection.py` and new `backend/workflow/evidence_batch_materializer.py` -- validate #31 inputs, call only the existing #30 exact/page builders, record lineage, apply precedence, and map legacy status only in projection.
- [x] existing #30 `backend/odp/query_client.py` builders -- use ledger-derived exact/frozen-page calls from the materializer; query, fingerprint, snapshot, and cursor failures are typed indeterminate inputs only.
- [x] `backend/api/v1/iii_collections.py` and response schemas -- add scoped recovery/read state with legacy mapping, materialization status, redacted refs, blocker, and recovery; reuse the existing Studio scope guard.
- [x] focused vertical, materialization API, and query-client tests plus disposable Postgres/`odp-query` smoke -- cover precedence, replay/amendment, redaction, chunks, and shortcut prohibition.

**Acceptance Criteria:**
- Given a complete scoped nonempty report/outcome set with no retained reject/DLQ and exact presence for every key, when Admin materializes, then a scoped immutable `completed` manifest retains revision/report/receipt/query/key-set/snapshot/hash lineage and bounded refs.
- Given explicit successful zero and empty key set without contradiction, when reconciled, then `completed_empty` has no refs and maps to legacy `completed`.
- Given missing/unknown input, outage, retention uncertainty, receipt conflict, incomplete coverage, or cursor failure/race, when materializing or recovering, then `indeterminate` maps to `blocked` with safe redacted recovery; no shortcut is terminal.
- Given explicit complete reject/DLQ facts with no unresolved key, when reconciled, then it is `partial` (or supported `failed_definitive`); accepted/duplicate never establishes presence.
- Given a late compatible fact, when reconciliation reruns, then it appends a revision without altering prior output or rebinding another attempt.

## Spec Change Log

## Design Notes

Frozen pages provide lineage; exact reconciliation proves only existence. Therefore page exhaustion and unavailable DLQ/retention cannot promote state.

## Verification

**Commands:**
- targeted Admin materializer and Studio tests -- expected: precedence, amendment, scope, recovery, and redaction pass.
- `cargo test -p odp-query` -- expected: exact presence/unknown and frozen cursor contracts remain green.
- disposable Postgres + `odp-query` smoke; Sentrux session start/end; independent review -- expected: sanitized manifests, fail-closed outage/cursor race, and no structural/authority bypass finding.

## Suggested Review Order

**Scoped reconciliation**

- Derives every ODP request from the immutable attempt, with terminal precedence fail-closed.
  [`evidence_batch_materializer.py:124`](../../backend/workflow/evidence_batch_materializer.py#L124)

- Validates expected keys, signed receipt coverage, and server-owned delegation scope.
  [`evidence_batch_materialization_facts.py:29`](../../backend/workflow/evidence_batch_materialization_facts.py#L29)

**Immutable presentation**

- Stores append-only revision manifests and paired reconciliation audit events.
  [`iii_collection.py:199`](../../backend/models/iii_collection.py#L199)

- Exposes scoped read, materialize, and recovery endpoints without raw ODP payloads.
  [`iii_collections.py:237`](../../backend/api/v1/iii_collections.py#L237)

**Persistence and proof**

- Creates the materialization tables with revision, hash, scope, and event constraints.
  [`b0c1d2e3f4a5_add_evidence_batch_materialization.py:17`](../../backend/migrations/versions/b0c1d2e3f4a5_add_evidence_batch_materialization.py#L17)

- Exercises completion, zero, outage recovery, rejection, and exact-key chunking.
  [`test_evidence_batch_materialization_api.py:40`](../../tests/integration/test_evidence_batch_materialization_api.py#L40)
