---
title: 'GitHub #29: Commit and Dispatch One Admin III Collection Attempt'
type: 'feature'
created: '2026-08-29'
status: 'done'
baseline_commit: 'b9ec317efda601322f6c314af8d18b5700b7aeb0'
review_loop_iteration: 0
context:
  - 'CONTEXT.md'
  - 'docs/wayfinder/iii-vertical/define-admin-iii-run-handoff.md'
  - 'docs/wayfinder/iii-vertical/define-cross-plane-correlation-and-idempotency.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Admin can construct an OpenCLI HDA III trigger envelope, but it does not own a durable immutable command/attempt, dispatch after commit, or accept correlated III lifecycle observations. An Admin crash, replay, or cancellation can therefore not prove which collection was requested or whether work was sent.

**Approach:** Add the bounded Admin-to-III command/attempt vertical for the existing `odp.collect::opencli_snapshot` function: persist immutable intent and a pending outbound transactionally, dispatch only after commit through a real III bridge, ingest replay-safe lifecycle observations, and show redacted scoped status. This ticket stops before collector final-report, ODP receipt/query, materialization, graph, and delivery authority.

## Boundaries & Constraints

**Always:** Version `IIICollectionCommandV1`, `IIICollectionAttemptV1`, lifecycle observations, and `VerticalStatusV1`; Admin allocates immutable command/attempt/task/trace IDs and canonical payload hash; persist command, attempt, outbound record, and `admin_requested` before any III request; reuse the current III 0.19 `worker.trigger` / `odp.collect::opencli_snapshot` route; require bridge lifecycle ingress to preserve supplied IDs/hash; deduplicate exact `(command_id, attempt_id, sequence)` ingress and reject changed payload/hash/scope; preserve append-only history; check cancellation immediately before dispatch; enforce existing workspace/project/workflow/run scope; redact payloads, secrets, raw evidence, and endpoints.

**Ask First:** Expanding into collector expected-key reports, `ODPIngressOutcomeReceiptV1`, direct ODP query/materialization, ResearchGraph, receiver/delivery, changing the existing collector function contract, or allowing a new III runtime/queue convention.

**Never:** Send before commit, create a direct collector/ODP/graph/receiver fallback, treat an III synchronous result, HTTP success, bridge reachability, or ingest count as completion, recompute IDs/hash on replay, let III allocate Admin identities, expose raw payload/evidence/secrets, or replace legacy workflow status semantics.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Submit | Valid scoped Run and canonical collection request | One immutable command and attempt, pending outbound, `admin_requested`, then III dispatch with identical supplied IDs/hash | Failure before transaction commit sends nothing |
| Resume | Committed unsent attempt after simulated crash | Same command/attempt/task/trace/hash is dispatched once eligible | No new intent or changed payload |
| Lifecycle replay | Same bridge event key and canonical content | Existing observation is returned; no duplicate state/history | Changed immutable content is a conflict |
| III unavailable | Committed pending attempt and dispatch failure | Redacted status is `bridge_unavailable` with a safe retry action | No direct fallback and no terminal collection state |
| Pre-dispatch cancellation | Command cancelled before worker trigger | Outbound remains undispatched and status records cancellation | Never invoke III |
| Status read | Scoped operator requests command status | `VerticalStatusV1` exposes state, blocking stage, safe evidence references/action, and side-effect uncertainty | Scope mismatch is rejected; secret/raw fields are absent |

</frozen-after-approval>

## Code Map

- `backend/api/v1/workflows.py` -- existing HDA trace endpoint and run-scoped route/access conventions; its trace path builds but does not dispatch.
- `backend/schemas/workflow.py` -- current HDA trace request/envelope types, including `taskId` and `traceId` that the new command must supply unchanged.
- `backend/workflow/opencli_hda_tracer.py` -- `_to_dispatch` emits the existing `odp.collect::opencli_snapshot` payload; extend through its established dispatch shape rather than create a second collector convention.
- `backend/models/workflow_run.py` and `backend/workflow/workflow_run_events.py` -- Admin append-only run-event allocator/replay rules; lifecycle observations must remain correlated Admin facts.
- `backend/models/intelligence.py`, `backend/workflow/intelligence_store.py`, and `backend/workflow/intelligence_outbox.py` -- existing durable commit-before-dispatch/outbox transaction and retry patterns to reuse for this command-specific persistence.
- `backend/services/acquisition_service.py` and `backend/api/v1/geo_acquisition.py` -- canonical request fingerprint, idempotency conflict, and cancellation-before-dispatch patterns.
- `iii/workers/collector-opencli/src/main.py` -- existing III 0.19 function registration and handler. It receives supplied `task_id`/`trace_id`; this ticket must extend lifecycle bridge behavior without treating its result as Admin completion.
- `iii/workers/odp-ingest-bridge/src/main.py` -- existing III bridge registration only; do not add receipt/report work owned by #31.
- `tests/integration/test_workflow_opencli_hda_trace_api.py` -- existing no-direct-ingest envelope contract.
- `tests/integration/test_workflow_event_spine_integration.py` and `tests/integration/test_workflow_native_intelligence_lifecycle.py` -- targeted persistence/replay and committed-outbox test patterns.

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/iii_collection.py`, model registration, and an Alembic migration -- persist immutable versioned command, attempt, outbound, and lifecycle ledger records with uniqueness constraints for attempt number and lifecycle replay.
- [x] `backend/schemas/iii_collection.py` -- define versioned submit, lifecycle, and redacted status contracts with explicit immutable identity/hash fields.
- [x] `backend/workflow/iii_collection_store.py` and `backend/workflow/iii_collection_dispatch.py` -- canonicalize once, atomically commit intent/outbox before send, reuse pending attempts after restart, invoke the existing III function path, and handle cancellation/replay/conflicts without fallback.
- [x] `backend/api/v1/...` -- add scope-guarded submit, resume, cancellation, lifecycle-ingress, and read-only status endpoints alongside the existing Studio/workflow run architecture.
- [x] `iii/...` bridge/collector integration -- accept and return Admin-supplied IDs/hash through `accepted`, `started`, and `returned` lifecycle observations using the existing 0.19 trigger/function mechanism.
- [x] targeted integration tests -- first make a real highest scoped Admin/III seam red for commit-before-send, supplied-ID lifecycle, replay conflict, cancellation-before-trigger, and redacted status; then make it green.

**Acceptance Criteria:**
- Given a fresh scoped collection request, when Admin submits it, then it commits immutable V1 command/attempt/outbox evidence before the first III invocation and sends no direct downstream request.
- Given Admin restarts after commit before dispatch, when pending work resumes, then the same attempt and hash dispatch; given a pre-commit failure, no III invocation occurs.
- Given III reports acceptance, start, return, or repeats one observation, when Admin ingests it, then supplied IDs/hash are validated, exact replay is idempotent, and a changed event is rejected.
- Given cancellation exists before outbound dispatch, when the dispatcher runs, then it records cancellation and never triggers III.
- Given a scoped status request after unavailable III, duplicate ingress, cancellation, or recovery pending, when Admin responds, then `VerticalStatusV1` is redacted and names the state, blocking stage, evidence references, recovery action, and side-effect uncertainty.

## Spec Change Log

## Design Notes

The external seam is a command dispatcher: callers submit immutable intent once and receive an Admin-owned command/attempt identity; dispatch, recovery, lifecycle validation, and redaction remain internal. The existing HDA dispatch envelope is the adapter to III, so the feature gains leverage without inventing a parallel trigger protocol.

`admin_requested` is a committed internal observation. `bridge_accepted`, `collector_started`, and `collector_returned` are correlated observations only; none can be promoted to collection completion in this ticket.

## Verification

**Commands:**
- targeted new Admin/III integration test -- expected: RED before implementation, then GREEN for commit-before-send, immutable replay, cancellation, and status.
- targeted existing HDA trace/event-spine tests -- expected: existing envelope/no-fallback and append-only event contracts remain green.
- real local III engine/worker smoke profile, when dependencies launch -- expected: Admin dispatch reaches the existing worker function and returns lifecycle observations with unmodified supplied IDs/hash.
- applicable typecheck/build and Sentrux `session_end` -- expected: no structural regression.

## Suggested Review Order

**Command transaction and dispatch**

- Trace immutable commit, atomic lease claim, and same-attempt recovery.
  [`iii_collection_store.py:185`](../../backend/workflow/iii_collection_store.py#L185)

- Confirm post-commit III invocation cannot overwrite lifecycle progress.
  [`iii_collection_dispatch.py:100`](../../backend/workflow/iii_collection_dispatch.py#L100)

**Ingress authority and worker bridge**

- Inspect strict scope/hash/sequence validation and redacted status projection.
  [`iii_collection_store.py:335`](../../backend/workflow/iii_collection_store.py#L335)

- Verify supplied correlation metadata is hashed and returned through the worker callback.
  [`main.py:53`](../../iii/workers/collector-opencli/src/main.py#L53)

- Check read-only scoped command, resume, cancellation, and lifecycle routes.
  [`iii_collections.py:56`](../../backend/api/v1/iii_collections.py#L56)

**Durability and proof**

- Review versioned ledger tables, uniqueness, and retention-safe foreign keys.
  [`a8b9c0d1e2f3_add_iii_collection_ledger.py:17`](../../backend/migrations/versions/a8b9c0d1e2f3_add_iii_collection_ledger.py#L17)

- Read the highest scoped Admin/III behavioral contract tests.
  [`test_iii_collection_vertical.py:110`](../../tests/integration/test_iii_collection_vertical.py#L110)
