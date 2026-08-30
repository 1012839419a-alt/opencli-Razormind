---
title: 'GitHub #35: Controlled Receiver Delivery with Verifiable Outcome'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 0
context: ['.claude/CLAUDE.md']
baseline_commit: 'e35f3ad4d93f4e7fc72f810822f335daa4e192b7'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #34 can freeze an independently approved, scope-bound `DeliveryAuthorizationDecisionV1`, but it deliberately has no execution, receiver, receipt, or outcome authority. Admin therefore cannot safely deliver the frozen projection or distinguish receiver acceptance from an HTTP acknowledgement.

**Approach:** Add a separate Admin-owned execution/result ledger and a real durable controlled-receiver v2 surface. The executor consumes one exact immutable decision and immutable target revision, reconstructs and verifies the stored sanitized projection on every attempt, then accepts only a fully verified signed receiver receipt.

## Boundaries & Constraints

**Always:** Treat `DeliveryAuthorizationDecisionV1` as the sole execution authority: load it in full scope with its exact target revision; rebuild the canonical `delivery-claim-manifest-v1` body from stored claim/manifest fields; and fail closed if its hash, decision binding, policy, target, or payload differs. Persist a reservation/lease plus exactly one immutable `DeliveryExecutionResult` for each attempted send, classifying transport, HTTP, receipt, and protocol evidence separately and exposing only final `accepted`, `rejected`, or `unknown`—never a business outcome. No decision or HTTP status yields `accepted` or `rejected`: only a fully verified signed receiver receipt can do so. Build v2 request MACs over canonical bytes plus explicit version, key ID, timestamp, nonce, operation ID, decision hash, and payload hash; resolve all keys from the revision's opaque credential reference and never persist, log, or return them.

Resolve endpoint identity only through a server-owned controlled-receiver registry with one exact HTTPS scheme/host/port/path and fixed public network scope. Reject client URLs/config, userinfo, fragments, query variance, mixed/private/loopback/link-local/multicast/reserved/unspecified IPv4/IPv6 answers, redirect/proxy/environment routing, DNS rebinding, and TLS SNI/Host identity mismatch; pin the validated peer socket. The receiver independently checks canonical body/schema, configured key ID, skew, durable nonce replay, operation/decision/payload binding, and constant-time MAC before side effects. Its durable key is `(operation_id, decision_hash)`: exact canonical duplicate returns its original signed receipt/status; changed MAC-bound content conflicts. Every receipt independently signs request identity/hash, receiver identity, durable status, receipt ID, and timestamp; only a fully verified receipt may yield `accepted` or `rejected`, and malformed, stale, missing, or mismatched receipts are `unknown` at every HTTP status.

Honor frozen `controlled-receiver-policy-v2`: at most three exact-idempotent sends; retry only timeout, network error, and HTTP 5xx after deterministic 1s then 2s waits. HTTP 4xx without a valid signed receipt is terminal `unknown`; a fully verified rejected receipt is terminal `rejected` regardless of HTTP class where the protocol permits it; any invalid or missing receipt is terminal `unknown` and non-retryable. Exhaustion requires reconciliation and blocks continuation; cancellation stops new attempts and is rechecked after an in-flight response; no automatic compensation. Concurrent/restart claims must serialize safely. A crash-ambiguous reservation is finalized `unknown` on recovery rather than silently resent. Exact completed invocation returns its ledger result; changed execution binding conflicts.

Studio execute/read/list/reconcile/status endpoints require `APPROVE_ACTIONS` for execution (or stricter existing execution permission) and `READ` for reads, enforce full scope and bounded opaque cursors, and redact secrets, raw payload/ODP, MACs, nonces, endpoint/IP, and receiver internals. The receiver is an independently authenticated durable route, not Studio-authenticated. Existing v1 notifier/rules/logs remain unchanged and non-research-authorized.

**Ask First:** Generalizing this controlled receiver into arbitrary webhooks, changing #34 decision/revision semantics or policy, weakening its network/MAC/receipt boundary, adding a workspace RBAC permission, or recording downstream business success.

**Never:** Execute from #33/V1 publish state, graph booleans, client-supplied actor/target/payload/policy, decision-shaped request data, or `NotificationRule`/`NotificationLog`; mutate/delete #34 records; follow redirects or use proxy/environment routes; accept an HTTP response or decision alone as controlled `accepted`/`rejected`; leak credential/key/signature/nonce/endpoint/raw payload; implement test-only receiver behavior instead of the durable v2 surface.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Verified delivery | Scoped frozen decision, matching revision/payload, valid accepted receipt | One attempt result and final `accepted` | No business outcome persisted |
| Verified receiver rejection | Fully verified signed rejected receipt at any protocol-permitted HTTP class | One terminal `rejected` result | No retry |
| Unverified nonretry response | HTTP 2xx or 4xx with missing, invalid, stale, or mismatched receipt | Terminal `unknown` | Fail closed; reconciliation required |
| Retryable failure | Timeout, network failure, or 5xx without a valid signed rejected receipt before three sends | Immutable result per send; retry after 1s then 2s | Exhaustion is blocked `unknown` |
| Replay/concurrency/restart | Same complete binding, racing caller, or recovered lease | Stable final/read result; no duplicate final attempts | Changed binding is conflict; ambiguous lease becomes unknown |
| Receiver replay/tampering | Same or changed `(operation, decision)` body; stale nonce/key/MAC/schema failure | Exact duplicate receipt or durable conflict/rejection | No side effect before validation |
| Hostile target/response | SSRF address, rebinding, redirect/proxy, or receipt signature alteration | No delivery authority/acceptance | Record safe classification only |
| Cancellation | Requested before or while send returns | Stop subsequent sends after observed result | Preserve cancellation/attempt evidence |

</frozen-after-approval>

## Code Map

- `backend/models/delivery_authorization.py:29-164` and `backend/workflow/delivery_authorization.py:366-459` — immutable target revision/decision fields and the exact canonical payload/hash derivation to consume without mutation.
- `backend/workflow/delivery_authorization.py:39-68` — frozen `controlled-receiver-policy-v2`, including receipt, retry, continuation, and no-compensation rules.
- `backend/schemas/delivery_authorization.py:34-133` and `backend/api/v1/delivery_authorization_routes.py:41-276` — scoped/RBAC/redacted Studio conventions; preserve the V1 read shape.
- `backend/models/iii_collection.py:13-129` — nearby scoped command/attempt/outbox/replay ledger and locking conventions; do not reuse its collection semantics.
- `backend/security/url_guard.py:119-432` and `tests/unit/security/test_url_guard.py:93-428` — reuse the existing public-address checks and DNS-pinned transport as the base, then add the receiver-specific exact registry and no-proxy/identity policy.
- `backend/notifiers/webhook_notifier.py:14-62`, `backend/models/notification.py`, and `backend/api/v1/notifications.py` — recorded no-reuse decision: legacy v1 notifier/rules/logs are mutable, secret-bearing execution and remain unchanged.
- `backend/config.py:7-83`, `backend/api/v1/__init__.py:1-93`, and `backend/migrations/versions/c1d2e3f4a5b6_add_delivery_authorization.py:17-117` — server-only configuration, router registration, and current restrictive migration conventions.

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/delivery_execution.py`, `backend/models/__init__.py`, and `backend/migrations/versions/*_add_delivery_execution.py` — add scoped execution claim/reservation, append-only immutable attempt-result rows, receiver durable request/nonce/receipt rows, restrict FKs, replay/binding/attempt uniqueness, and indexes without modifying #34 rows.
- [x] `backend/config.py` and `backend/security/controlled_receiver.py` — define the server-owned endpoint/key/receipt-key registry and opaque credential resolver; canonicalize/MAC/verify v2 requests and receipts; layer exact HTTPS identity, DNS all-answer validation, pinned direct connection, no proxy/redirect, and response identity checks on the existing URL guard transport.
- [x] `backend/workflow/delivery_execution.py` and `backend/schemas/delivery_execution.py` — reconstruct/verify frozen payloads; claim/recover/cancel/reconcile execution atomically; record classifications/results; enforce policy retry/backoff and redacted Studio contracts.
- [x] `backend/api/v1/delivery_execution_routes.py`, `backend/api/v1/controlled_receiver_routes.py`, and `backend/api/v1/__init__.py` — expose scoped Studio execute/read/list/reconcile/status APIs and separately authenticated receiver v2 delivery/status routes, preserving v1 notifier behavior.
- [x] `tests/unit/test_delivery_execution.py`, `tests/unit/test_controlled_receiver.py`, `tests/unit/security/test_controlled_receiver_transport.py`, and `tests/integration/test_delivery_execution_api.py` — TDD ledger/retry/cancellation/restart/replay; receipt-only accepted/rejected classification including unverified 2xx/4xx as terminal unknown and 5xx retry; MAC/nonce/receipt validation; IPv4/IPv6/rebind/redirect/proxy resistance; RBAC/redaction/pagination; and real sender-to-durable-receiver restart duplicate smoke.

**Acceptance Criteria:**
- Given a valid scoped frozen decision and configured controlled receiver, when Studio executes it, then only a fully verified signed receiver receipt may determine `accepted` or `rejected`; an immutable result exists for every network attempt.
- Given an unverified HTTP 2xx or 4xx response, a retryable fault, duplicate/concurrent invocation, restart/crash reservation, cancellation, or reconciliation request, when lifecycle state changes, then 2xx/4xx are terminal `unknown`, only timeout/network/5xx follows policy backoff, and idempotency, final-result stability, and blocked unknown continuation are preserved.
- Given receiver auth failures, a duplicate/conflicting delivery, a tampered/stale receipt, or a valid signed rejected receipt, when the receiver or executor processes it, then only the valid receipt can yield `rejected`, no unverified side effect becomes accepted, and all responses remain redacted.
- Given hostile resolution/routing input or an unpinned peer change, when the sender validates/connects, then no private or identity-mismatched destination is contacted and no proxy or redirect route is used.

## Spec Change Log

## Design Notes

The execution claim is deliberately separate from immutable result evidence: reserve before a send, insert exactly one immutable result after its observed return, and resolve a recovered reservation with an immutable unknown result rather than guessing whether the receiver acted. The receiver can safely return its same durable signed receipt for exact duplicates, but execution never treats that receiver idempotency as permission to bypass an unresolved `unknown` state. The v1 notifier is explicitly not reused; the existing `url_guard` validation and pinned transport are reused only beneath a stricter controlled-receiver registry that forbids its generic URL, proxy, and routing flexibility.

## Verification

**Commands:**
- `alembic upgrade head` — expected: new execution/receiver ledger constraints apply to a disposable database.
- `uv run --extra dev pytest --no-cov tests/unit/test_delivery_execution.py tests/unit/test_controlled_receiver.py tests/unit/security/test_controlled_receiver_transport.py tests/integration/test_delivery_execution_api.py` — expected: policy, security, redaction, and durable sender→receiver/restart contracts pass.
- `uv run --extra dev pytest --no-cov tests/unit/test_delivery_authorization.py tests/integration/test_delivery_authorization_api.py tests/unit/test_research_graph_v2.py tests/integration/test_research_graph_v2_api.py` — expected: #34/#33 authorization and pinned-fold behavior remain unchanged.
- `uv run --extra dev pytest --no-cov tests/integration/test_evidence_batch_materialization_api.py tests/integration/test_iii_collection_vertical.py tests/integration/test_iii_collection_cancellation.py` — expected: #32 collection/reconciliation behavior remains unchanged.
- Sentrux session start/end for `backend` and an adversarial security review — expected: no authority-boundary or structural regression.

**Completed evidence (2026-08-30):**
- `uv run alembic upgrade head` applied through `e3f4a5b6c7d8` successfully.
- `uv run --extra dev pytest --no-cov tests/unit/test_delivery_execution.py tests/unit/test_controlled_receiver.py tests/unit/security/test_controlled_receiver_transport.py tests/integration/test_delivery_execution_api.py` — 22 passed; includes a durable executor→receiver signed-receipt/replay proof.
- `uv run --extra dev pytest --no-cov tests/unit/test_delivery_authorization.py tests/integration/test_delivery_authorization_api.py tests/unit/test_research_graph_v2.py tests/integration/test_research_graph_v2_api.py` — 33 passed.
- `uv run --extra dev pytest --no-cov tests/integration/test_evidence_batch_materialization_api.py tests/integration/test_iii_collection_vertical.py tests/integration/test_iii_collection_cancellation.py` — 20 passed, 1 skipped.
- Fresh detached-worktree verification at `10db33e5`: `uv run alembic upgrade head` applied through `f4a5b6c7d8e9`; targeted Python compilation passed; the controlled delivery matrix passed **88 tests**.
- Regression matrix for #32/#33 passed **29 tests, 1 skipped**; `npm run typecheck` passed.
- `sentrux scan backend` completed with quality signal `6200`, zero cycles, and zero unresolved imports.
- No independent adversarial review produced a completed report before its lagging workers were cancelled; GitHub #35 remains open pending that independent sign-off.
