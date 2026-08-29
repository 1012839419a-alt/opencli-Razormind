---
title: 'GitHub #31: Collector Expected Keys and Signed Ingress Outcomes'
type: 'feature'
created: '2026-08-30'
status: 'in-review'
baseline_commit: 'cd380a984f788eaa16022ca08048ba772db5ba7d'
review_loop_iteration: 0
context:
  - 'docs/wayfinder/iii-vertical/non-bypass-iii-vertical-spec.md'
  - 'docs/wayfinder/iii-vertical/define-admin-iii-run-handoff.md'
---

<frozen-after-approval reason="human-owned intent — approved 2026-08-30; do not modify unless human renegotiates">

## Intent

**Problem:** The #29 Admin-to-III command ledger can prove only that a collection was requested and that execution observations arrived. The real collector currently returns unbounded collector/ingest dictionaries, and `odp-ingest` returns aggregate enqueue observations without a signed, replay-safe Admin fact. Consequently, zero, rejection, duplicate, crash-after-ingest, or a synchronous successful return can be mistaken for final evidence.

**Approach:** Extend the existing Admin → III collector → III ingest bridge → Rust `odp-ingest` route with two bounded V1 contracts: a final immutable expected-key report emitted by the collector and an authoritative signed per-key ingress-outcome receipt emitted by `odp-ingest`. The authenticated III bridge transports those facts to Admin, which validates their immutable #29 correlation, persists replay-safe ledger records, and exposes only redacted nonterminal state.

## Boundaries & Constraints

**Always:** Preserve #29 Admin-owned `command_id`, `attempt_id`, `task_id`, `trace_id`, scope, and immutable payload hash; version every new contract, canonicalize/hash its immutable content once, bound expected keys and rejection facts, and use stable replay identities. A report contains the exact source/event key set (or explicit successful zero), key-set hash, item/zero/reject counts, sequence, time, and report hash. An `ODPIngressOutcomeReceiptV1` is signed by an authenticated `odp-ingest` producer and contains receipt/idempotency identities, producer/key identity, all required correlations, expected-key-set hash, per-key `accepted`/`duplicate`/`rejected` outcome plus bounded rejection reason, time, receipt hash, and signature. Admin accepts only correlation/hash/scope-valid, signature-valid reports/receipts; identical replay is idempotent and changed content is a conflict. Status remains scope-authorized, read-only, append-only, and redacted.

**Ask First:** Altering #29 command/attempt identity or lifecycle meanings; selecting a new signing/key-management mechanism rather than the repository's established secure configuration; changing ODP PostgreSQL/store semantics; retaining raw payloads, raw records, or unbounded rejection bodies; expanding the status view into materialization, graph, delivery, receiver, or query ownership.

**Never:** Treat HTTP 2xx, III trigger return, collector `ok`, ingest accepted/duplicate counts, a report, a receipt, or a missing callback as PostgreSQL persistence, empty final materialization, or a terminal run result. Do not add direct Admin→collector/ODP paths, permit unsigned producer callbacks, infer duplicates from time/order, recompute stored hashes on replay, or include #32 reconciliation/materialization/query, ResearchGraph, delivery, receiver, or shared-environment acceptance work.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh nonempty collection | Admin-correlated items enter the current collector route | Collector sends events and emits one bounded `CollectorFinalExpectedKeyReportV1`; `odp-ingest` produces signed exact per-key ingress receipt | Both Admin facts remain nonterminal pending #32 reconciliation |
| Declared zero | Successful collector returns exactly no items | Report declares empty immutable set and zero result; no fabricated accepted receipt entries | Still nonterminal; absence of records/receipts cannot be called materialized empty |
| Ingest before collector return/crash | Ingress outcome reaches bridge before report, or collector dies after ingest | Authenticated receipt is retained as late/unmatched/nonterminal evidence; missing report blocks finalization | Do not erase, infer no side effect, or synthesize a report |
| Rejection and duplicate | `odp-ingest` classifies individual keys | Receipt preserves exact outcome per key and bounded rejection fact | Duplicate is an ingress observation, not exact-record proof |
| Replay/tamper | Same report/receipt identity is redelivered, or immutable content/signature/scope differs | Exact canonical replay returns stored ledger fact; changed content is rejected | No overwrite or second ledger observation |
| Status read | Authorized scoped operator reads command | `VerticalStatusV1` names a blocking nonterminal collector/ingress stage and safe evidence references | Reject cross-scope access and redact signatures, secrets, raw keys/payloads, and rejection details |

</frozen-after-approval>

## Code Map

- `iii/workers/collector-opencli/src/main.py` -- real `odp.collect::opencli_snapshot` handler converts OpenCLI items to Record v2, triggers the existing ingest bridge, and currently emits only lifecycle/aggregate return data.
- `iii/workers/odp-ingest-bridge/src/main.py` and `iii/lib/odp_record.py` -- authenticated III ingress route and HTTP adapter; carry collector/Admin correlation without inventing an alternate path.
- `odp-rs/crates/odp-ingest/src/handlers.rs`, `odp-rs/crates/odp-ingest/src/main.rs`, and `odp-rs/crates/odp-contracts/src/lib.rs` -- authoritative validation/enqueue classification and the appropriate V1 signed receipt producer boundary.
- `backend/models/iii_collection.py`, `backend/schemas/iii_collection.py`, `backend/workflow/iii_collection_store.py`, and a new migration -- existing #29 immutable command/attempt/lifecycle ledger patterns to extend with report/receipt retention and replay uniqueness.
- `backend/api/v1/iii_collections.py` and `backend/api/v1/__init__.py` -- authenticated ingress and scoped redacted Admin read routes.
- `tests/integration/test_iii_collection_vertical.py` plus targeted collector/ingest contract tests -- highest public Admin/III seam and real producer/bridge behavior.

## Tasks & Acceptance

**Execution:**
- [ ] `odp-rs/crates/odp-contracts/src/lib.rs` and `odp-rs/crates/odp-ingest/...` -- define canonical V1 receipt/key/outcome types, bounded reason policy, producer identity, hash, and signature; classify actual validation/enqueue outcomes exactly once per input key.
- [ ] `iii/workers/collector-opencli/src/main.py` and `iii/workers/odp-ingest-bridge/src/main.py` -- produce the final bounded report from the actual converted event set and transport real signed receipt/report observations through the existing III route, including ingress-before-return behavior.
- [ ] `backend/models/iii_collection.py`, migration, schemas, store, and API -- authenticate/validate producer facts, enforce #29 scope/correlation/hash, append replay-safe retained ledger records, and project redacted `VerticalStatusV1` without terminal inference.
- [ ] targeted changed-contract tests -- make the Admin/III public seam red, then prove valid/zero/reject/duplicate, late/missing report, tampered/conflicting replay, scope rejection, and nonterminal redacted status.

**Acceptance Criteria:**
- Given a fresh #29-scoped attempt, when its real collector converts source items, then Admin can retain one bounded immutable expected-key report whose key set/hash/counts/correlation identify the actual event set.
- Given `odp-ingest` validates/enqueues that set, when it reports per-key outcomes through the bridge, then Admin accepts only a producer-authenticated signed receipt matching the immutable command/attempt/task/trace/payload hash/scope and persists exact replay once.
- Given changed receipt/report bytes, producer/signature, correlation, scope, or replay content, when callback ingestion occurs, then Admin rejects it and does not mutate retained facts.
- Given ingress precedes collector return, collector crashes after ingest, a report is absent, a receipt duplicates, or enqueue rejects, when status is read, then the view is redacted and nonterminal; it never claims record persistence, completed empty, final materialization, graph eligibility, or delivery.

## Spec Change Log

## Design Notes

The expected-key set is a collector completion boundary, while the ingress receipt is an ODP validation/enqueue boundary. Their hashes deliberately join through the immutable #29 attempt but neither substitutes for #32 exact-record reconciliation. Receipt signing authenticates the authoritative producer, not the III transport; Admin validates the signature before durable replay handling.

**Concurrent-worktree overlap risk:** the known dirty tree has 45 unstaged and 40 untracked paths, including `backend/api/v1/__init__.py`, `backend/api/v1/studio.py`, `backend/config.py`, `backend/main.py`, `backend/schemas/workflow.py`, `docker-compose.yml`, and ODP Rust files. #30 is concurrently changing ODP query/reconciliation code. This isolated branch begins from the clean #29-hardened commit and must retain only #31 files; it does not touch the shared tree.

## Verification

**Commands:**
- targeted `test_iii_collection_vertical.py` and newly added contract tests -- expected: valid receipt/report behavior, conflict rejection, and all named nonterminal cases are green.
- focused Rust `odp-ingest`/`odp-contracts` tests -- expected: exact accepted/duplicate/rejected per-key classification and signature verification pass.
- disposable real III + `odp-ingest` smoke -- expected: actual collector/bridge/ingest path produces signed facts; collector return or HTTP success alone never changes terminal state.
- code review and Sentrux `session_end` for all #31 paths -- expected: no security/structural regression before issue closure.
