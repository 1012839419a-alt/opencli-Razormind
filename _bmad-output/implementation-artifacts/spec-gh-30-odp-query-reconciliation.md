---
title: 'Scoped ODP Record Reconciliation Through odp-query'
type: 'feature'
created: '2026-08-29'
baseline_commit: 'b9ec317efda601322f6c314af8d18b5700b7aeb0'
status: 'in-review'
review_loop_iteration: 0
context: ['CONTEXT.md', 'docs/PLAN_odp_enterprise.md', 'docs/wayfinder/iii-vertical/define-odp-to-evidencebatch-materialization.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Admin has no governed way to establish ODP PostgreSQL record presence. Its legacy records and control-metrics paths are separate stores/read models, while `odp-store` is the only ODP schema and write owner.

**Approach:** Add an independent, read-only Rust `odp-query` service and the narrow Admin-mediated presentation path. It accepts only machine-trusted, delegated, bounded exact-key, attempt-page, or DLQ reconciliation requests, returns server-redacted record references, and fails closed for every unsupported or uncertain condition.

## Boundaries & Constraints

**Always:** Keep `odp-store` as schema/writer owner and leave Record v2 authoritative fields untouched. Authorize Admin-to-query machine identity and the delegated workspace/project/workflow/run/batch/attempt scope. Derive fixed mode inputs in Admin rather than accepting browser predicates. Exact lookup may say only `present`; it never classifies inserted, duplicate, completion, empty result, or page order. Freeze first-page `as_of`; bind opaque cursors to fingerprint/scope and order strictly by `(committed_at,id)`. Apply server field allowlists, JSONB redaction, page/key/response limits, and explicit retention/DLQ unknown state.

**Ask First:** Expand the trusted caller identity beyond the configured Admin machine credential, add a signed user-delegation format, or expose an additional/general-purpose or client-predicate-driven browser ODP query surface. The ticket's derived, fixed, scoped Admin presentation API is approved.

**Never:** Share an Admin/`odp-store` DB session; add direct Admin SQL or arbitrary predicates/SQL/JSONB paths; use ODP notifications, Redis, no rows, timestamp, or cursor order as finality; add `ODPIngressOutcomeReceiptV1`, EvidenceBatch materialization, ResearchGraph, delivery, or other #31/#32 work.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exact presence | Authorized bounded `(source_id,event_id)` key is committed | Sanitized reference classified `present` only | No completion/new/duplicate implication |
| First attempt page | Authorized task/trace/allowed sources | Response fixes `as_of`, fingerprint, bounded ordered records, opaque cursor | Page is diagnostic, never a watermark |
| Later page | Matching opaque cursor and delegation | Uses original snapshot and exclusive `(committed_at,id)` position | Mismatched, expired, tampered, or scope-rebound cursor fails closed |
| No exact row | Retention/deletion cannot be proven | Explicit `unknown` retention state | Never infer absent, zero, or rejection |
| DLQ | Matching durable DLQ row under bounded scope | Sanitized `dlq` classification with retention facts | Unknown/missing retention or unmatched DLQ remains `unknown` |
| Unsafe request | Browser credential, untrusted caller, extra predicate, raw JSONB request, or oversized result | No ODP data returned | Redacted authorization/validation failure |

</frozen-after-approval>

## Code Map

- `odp-rs/Cargo.toml` -- workspace membership/dependencies; add an independently deployable `odp-query` crate without making `odp-store` an HTTP reader.
- `odp-rs/crates/odp-query/{Cargo.toml,src/main.rs,src/query.rs,src/types.rs}` -- new deep module: trusted internal HTTP seam, fixed request modes, cursor codec, parameterized read queries, and response redaction.
- `odp-rs/crates/odp-store/src/writer.rs:migrate` -- schema owner; add only idempotent query-plan indexes for attempt page and exact DLQ lookup, retaining `odp_records` authority and unique `(source_id,event_id)`.
- `odp-rs/crates/odp-contracts/src/lib.rs` -- Record v2 source/event/task/trace fields; intentionally unchanged.
- `backend/api/v1/studio_workflows.py` and `backend/api/v1/__init__.py` -- existing scoped Studio seam/router; use only a constrained Admin client/proxy path. Both already contain unrelated worktree modifications and need precise non-overlapping edits.
- `backend/security/fleet_auth.py` -- existing Admin request authentication pattern; reuse rather than creating a direct database or browser trust path.
- `tests/unit/odp/` and `tests/integration/` -- public Admin authorization/contract tests; new Rust query tests cover exact, snapshot/cursor, redaction, DLQ/retention, and rejection behavior.

## Tasks & Acceptance

**Execution:**
- [x] `odp-rs/Cargo.toml`, `odp-rs/crates/odp-query/**` -- added a read-only Rust service with one fixed internal operation, machine/delegation validation, bounded modes, scope-bound cursor, sanitized projections, and no general query surface.
- [x] `odp-rs/crates/odp-store/src/writer.rs` -- added idempotent query-plan indexes for attempt-page and exact DLQ reconciliation without changing Record v2 or ownership.
- [x] `backend/api/v1/odp_reconciliation.py`, `backend/odp/query_client.py` -- added the scoped public Admin proxy/read path; it derives ledger scope and rejects caller scope/predicate escalation.
- [x] focused Rust and highest-public-Admin contract tests -- RED compiler/decoder/validator failures were fixed; containerized Rust tests, Admin contracts, and disposable Postgres service smoke passed.

**Acceptance Criteria:**
- Given a fresh authorized Admin context, when it requests an in-scope bounded exact key, attempt page, or DLQ result, then only a redacted, bounded response from `odp-query` is observable and Admin does not access ODP tables directly.
- Given an exact committed key, when reconciled, then the result states record presence only and does not state completion, empty, inserted, duplicate, or new.
- Given an attempt page begins, when subsequent pages are requested, then every page uses the original `as_of` and fingerprint-bound opaque cursor ordered by `(committed_at,id)`; any cursor mismatch or page race fails closed.
- Given unknown retention, unknown DLQ, a query outage, unsafe trust/scope, raw JSONB demand, or a limit breach, when queried, then no unredacted ODP data or optimistic classification is returned.

## Spec Change Log

## Design Notes

The `odp-query` module is deliberately deep: Admin learns one delegated fixed-mode interface while the module owns credential validation, scope binding, SQL shape, cursor integrity, and redaction. The query response contains references rather than payloads, so the public Admin seam cannot become a generic ODP browser.

## Verification

**Commands:**
- `cargo test -p odp-query` -- expected: exact, snapshot/cursor, redaction, DLQ/retention, and authorization contracts pass.
- `pytest <focused Admin contract test>` -- expected: public scoped proxy accepts only derived bounded modes and rejects bypass input.
- `docker compose --profile odp ...` plus a disposable Postgres query smoke -- expected: running service returns a sanitized exact/paged/DLQ result against ODP schema.
- `npm run typecheck` and relevant backend checks -- expected: Admin route/client contract remains valid.
