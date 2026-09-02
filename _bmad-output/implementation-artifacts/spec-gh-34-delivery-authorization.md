---
title: 'GitHub #34: Persist Frozen Delivery Authorization Decisions'
type: 'feature'
created: '2026-08-30'
baseline_commit: 'd21adbc0daa8732b3d82177759ec8e260bc270b1'
status: 'done'
review_loop_iteration: 0
context:
  - 'docs/wayfinder/iii-vertical/define-researchgraph-delivery-authority.md'
  - '_bmad-output/implementation-artifacts/spec-gh-33-researchgraph-v2-evidence-review-pinned-fold.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Admin has materialized evidence and a governed, pinned ResearchGraph V2 fold but lacks a durable authority boundary for a side effect. Existing notification rules are mutable, global execution configuration, so they cannot prove what operation, destination, policy, evidence, payload, or independent approver was frozen before any delivery.

**Approach:** Add one Admin-owned append-only `DeliveryAuthorizationDecisionV1` module. It server-resolves a minimally scoped outbound target revision and policy, reads the exact #33 pinned fold, derives eligible verified claims/manifests, sanitizes a deterministic claim-manifest payload, and persists one immutable authorization decision. It does not send anything.

## Boundaries & Constraints

**Always:** Bind each decision to immutable `operationId` and idempotency key; full workspace/project/workflow/version/run scope; target ID/revision/endpoint identity/non-secret config hash; policy version/snapshot/hash; exact pin sequence/research revision/manifest-set hash; selected verified claim IDs/content hashes and manifest tuples; canonical sanitized payload manifest/hash; server-derived approval actor/principal/capability/time; decision hash and creation time. Resolve caller identity/capability with existing workspace RBAC, require `APPROVE_ACTIONS`, and reject an approver who proposed any selected graph claim. Call #33 `read_research_graph_v2(..., require_pinned_reference=True)` with a server-derived full scope and exact expected pin; only an unblocked pin and nonempty selected `verified` claims are eligible. Re-resolve target revision and policy at each request, then store their frozen values. Replaying the exact binding returns the same decision; any changed operation, target/revision, policy, payload, approval, pin, claim, or manifest conflicts without overwrite. Reads and lists are scope-authorized, redacted, bounded, and cursor-paginated.

**Ask First:** Adding an actual receiver protocol, HTTP call, execution result, business outcome, generic notification migration, new workspace RBAC permission, or allowing a different payload projection/target kind than the controlled receiver contract.

**Never:** Reuse inbound `Source`/`SourceBinding` as an outbound target; reuse `NotificationRule`/`NotificationLog`; trust client actor, capability, target config, policy snapshot, graph boolean, V1 publish result, raw ODP identifier/payload/signature, or unmaterialized evidence. Do not authorize an absent/blocked/stale/mismatched pin, current-manifest amendment, proposed/superseded/rejected/retracted claim, empty/unknown evidence, cross-scope target/run, or self-approval. No #34 route/service may execute delivery, contact a receiver, create a notification log, report delivery, or write an outcome.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Fresh authorization | Scoped current controlled-receiver revision; exact unblocked pin; selected verified claims; authorized independent approver | Create exactly one redacted immutable decision with all frozen hashes/lineage | No receiver/notification/outcome side effect |
| Exact replay / concurrent submit | Same operation and canonical binding, including one racing request | Return the original decision; one persisted row | Unique conflict is re-read and accepted only if every frozen field matches |
| Binding drift | Changed operation, target/revision, policy hash, sanitized payload, pin, claim/manifest, or approver | Preserve original decision | `409`; caller must allocate a new operation |
| Graph or approval denial | Missing/blocked/stale pin; manifest amendment; empty/non-verified claim; V1 boolean; client authority; self/unauthorized/cross-scope actor | Authorize nothing | Fail closed before insert with safe error |
| Studio presentation | Scoped decision/target read or list | Return bounded redacted summaries and opaque next cursor | Never return endpoint credentials, payload body, ODP IDs, signatures, raw policy, or approval secrets |

</frozen-after-approval>

## Code Map

- `backend/workflow/research_graph_v2.py:229-284,428-469` -- reuse the exact scoped pinned-reference and current-manifest freshness gate unchanged; V2 is read authority only, never delivery authorization.
- `backend/schemas/research_graph_v2.py:38-110` -- V2 claim state, proposer ID, manifest tuple, and redacted pin contracts; use only verified claims and compare decision approver to proposer evidence.
- `backend/api/v1/research_graph_v2_routes.py:34-117` and `backend/api/v1/iii_collections.py:70-100,265-298` -- established full Studio scope, authenticated RBAC, opaque cursor, bounded redacted-list patterns.
- `backend/security/workspace_rbac.py:14-91` -- existing `APPROVE_ACTIONS`, authenticated membership, and permission enforcement; do not accept request authority fields.
- `backend/models/notification.py:9-50` and `backend/api/v1/notifications.py:29-92` -- read-only counterexample: global mutable execution rules/logs with raw secret-bearing config; deliberately not a target or decision seam.
- `backend/models/source_binding.py:1-119` -- read-only counterexample: revision convention is inbound-source domain, not delivery direction.
- `backend/models/__init__.py:20-29` and `backend/migrations/versions/b0c1d2e3f4a5_add_evidence_batch_materialization.py:17-87` -- register new Admin models and follow current immutable migration/restrict-FK/index conventions.

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/delivery_authorization.py`, `backend/models/__init__.py`, and `backend/migrations/versions/*_add_delivery_authorization.py` -- add workspace-owned `DeliveryTarget` and immutable revision rows (controlled-receiver identity, non-secret config hash, server-side credential reference only), plus append-only scoped `DeliveryAuthorizationDecisionV1`; use restrict FKs and unique target-revision, scoped operation/idempotency, and decision-hash constraints/indexes.
- [x] `backend/schemas/delivery_authorization.py` and `backend/workflow/delivery_authorization.py` -- define the narrow create/read/list contracts and one cohesive resolver/store: canonicalize a projection made only of schema version, selected claim IDs/content hashes, and manifest hashes; reject secret/raw-ODP fields; derive policy snapshot and approval evidence server-side; invoke #33 exact pin read; lock/replay atomically; never import execution/notifier code.
- [x] `backend/api/v1/delivery_authorization_routes.py` and `backend/api/v1/__init__.py` -- add authenticated target configuration and scoped decision create/read/list routes. Target configuration requires `MANAGE_CONFIGURATION`; authorization requires `APPROVE_ACTIONS`; reads require `READ`; all route scope and response projections are server-owned/redacted.
- [x] `tests/unit/test_delivery_authorization.py` and `tests/integration/test_delivery_authorization_api.py` -- TDD the resolver and actual authenticated Studio/database API, including no delivery side effect and target/decision redaction/pagination.

**Acceptance Criteria:**
- Given an independent `APPROVE_ACTIONS` member, current controlled target, exact unblocked #33 pin, and verified scoped claims, when they authorize one operation, then Admin stores one immutable side-effect authorization containing every required scope, target, policy, graph, claim/manifest, payload, and actor binding, with no execution/outcome fact.
- Given a replay, changed request field, or concurrent duplicate, when authorization is attempted, then the exact replay is stable, a changed binding is `409`, and database uniqueness leaves one decision only.
- Given target/policy/payload/pin/manifest drift, a stale/amended graph, empty/unknown/non-verified claim, V1 publish boolean, client actor/capability/config, self-approval, absent permission, or foreign scope, when submitted, then no decision is written.
- Given a scoped list/read, when an authorized Studio user requests decisions or targets, then cursor limits and scope are enforced and output omits credentials, raw payload/ODP/signatures, and execution/business-outcome language.

## Spec Change Log

## Design Notes

A durable outbound target is absent: `NotificationRule` is global, mutable, stores secret-bearing config, and its logs are execution outcomes; `webhooks.py` is ingress-only. `Source`/`SourceBinding` are revisioned but inbound collection identity, so repurposing them would invert their meaning. The smallest unambiguous boundary is a new workspace-owned controlled-receiver `DeliveryTarget` with immutable revision. It freezes endpoint identity plus a non-secret canonical config hash and a server-side credential reference, never the secret. #35 may consume the frozen decision; #34 must not call it.

## Verification

**Commands:**
- `uv run --extra dev pytest --no-cov tests/unit/test_delivery_authorization.py tests/integration/test_delivery_authorization_api.py` -- expected: durable replay, concurrency, graph/approval denial, scope/redaction/pagination, and zero-delivery contracts pass.
- `uv run --extra dev pytest --no-cov tests/unit/test_research_graph_v2.py tests/integration/test_research_graph_v2_api.py` -- expected: #33 exact pin, manifest freshness, V2 review, and V1-advisory behavior remain unchanged.
- authenticated Studio API smoke against the test app and disposable database -- expected: create target, authorize, replay, read/list and fail-closed paths behave as above; no receiver/notification/outcome record exists.
- Sentrux session start/end for `backend` and the focused changed-contract test set -- expected: no structural or authority-boundary regression.

## Suggested Review Order

**Authorization boundary**

- Server resolves every frozen authorization binding and rejects drift before persistence.
  [`delivery_authorization.py:453`](../../backend/workflow/delivery_authorization.py#L453)

- API routes derive identity and enforce distinct configuration, approval, and read permissions.
  [`delivery_authorization_routes.py:92`](../../backend/api/v1/delivery_authorization_routes.py#L92)

**Freshness and durability**

- Cross-dialect write barrier serializes current-run freshness-sensitive writers.
  [`workflow_run_lock.py:11`](../../backend/workflow/workflow_run_lock.py#L11)

- Append-only models and restrict-scoped immutable decision storage define the durable boundary.
  [`delivery_authorization.py:19`](../../backend/models/delivery_authorization.py#L19)

- Migration creates immutable target revisions and frozen authorization records.
  [`c1d2e3f4a5b6_add_delivery_authorization.py:18`](../../backend/migrations/versions/c1d2e3f4a5b6_add_delivery_authorization.py#L18)

**Contracts and proof**

- Strict opaque receiver references prevent raw endpoint and credential persistence.
  [`delivery_authorization.py:18`](../../backend/schemas/delivery_authorization.py#L18)

- Authenticated API tests prove redaction, replay, denial, immutability, and zero legacy delivery records.
  [`test_delivery_authorization_api.py:31`](../../tests/integration/test_delivery_authorization_api.py#L31)

- Unit and real file-SQLite tests prove fail-closed evidence and run-lock interleaving.
  [`test_delivery_authorization.py:57`](../../tests/unit/test_delivery_authorization.py#L57)
  [`test_workflow_run_lock.py:10`](../../tests/unit/test_workflow_run_lock.py#L10)
