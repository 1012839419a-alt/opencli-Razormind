---
title: 'Deliver Certified Records to Feishu Bitable'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: '9ef04c64d2a0cdc52add8a074202849c339454a9'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** OpenCLI persists certified Gaojixing Records locally but has no reusable Feishu Bitable destination for collaborative delivery.

**Approach:** Add an encrypted connection under “Provider 与连接” and a real workflow sink referencing an existing app/table. Deliver stored Record refs through official APIs with typed failures, idempotency, redaction, and traceable attempts.

## Boundaries & Constraints

**Always:** Encrypt `app_secret` with existing Fernet; never return secrets or tenant tokens. Fix the API host, validate targets server-side, deliver only materialized Record refs, preserve run/Record/evidence identity, and make retries idempotent per target/Record. Nodes store only connection/target references and non-secret mapping. Failures are typed and fail closed.

**Ask First:** Live calls with real credentials; remote table creation/change/deletion; OAuth/user-token auth; automatic published-workflow changes.

**Never:** Reuse the webhook notifier; expose credentials in nodes, notifier JSON, logs, traces, URLs, or frontend state; disguise a destination as a DataSource; require Feishu in existing Gaojixing templates; send archive files or screenshot bytes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid connection | App ID/secret and encryption configured | Save; reads expose only masked metadata | Missing encryption key returns 503 without persistence |
| Target validation | Enabled connection and app/table IDs | Acquire tenant token and verify fields | Auth, permission, missing table, timeout, and business codes are redacted |
| Certified delivery | Sink receives stored Gaojixing Record refs | Batch-create mapped rows and attempts | Malformed upstream fails before network delivery |
| Retry/resume | Same destination/table/Record is executed again | Return prior successful attempt and create no duplicate row | In-flight/failed attempts remain observable and safely retryable |
| Missing configuration | Disabled/missing connection or target/mapping | Workflow node is blocked before outbound request | Trace contains a typed non-secret block reason |

</frozen-after-approval>

## Code Map

- `backend/auth/crypto.py`, `backend/models/provider.py:10` -- Fernet and masked-read patterns.
- `backend/models/delivery_connection.py` -- new connection and idempotent delivery-attempt models; unique key includes connection, app, table, and Record.
- `backend/migrations/versions/d1e2f3a4b5c6_add_delivery_connections.py` -- create connection/attempt tables from merged head `c0d1e2f3a4b5`.
- `backend/schemas/delivery_connection.py`, `backend/api/v1/delivery_connections.py` -- write-only secret CRUD, masked reads, target probe.
- `backend/services/feishu_bitable_delivery.py` -- fixed-host tenant-token and Bitable batch-create client.
- `backend/workflow/runtime_registry.py:64` -- add a distinct REAL delivery binding resolved from connection/target references.
- `backend/workflow/opencli_hda_tracer.py:3624` -- execute after Record Sink; persist attempts and redacted traces.
- `frontend/app/(app)/providers/catalog/page.tsx` and `frontend/components/providers/rss-generator-provider-panel.tsx:74` -- mount a Feishu connection panel using existing create/edit/test/status patterns.
- `frontend/lib/api/{types,endpoints,hooks}.ts` -- write-only credentials and query invalidation.
- `frontend/lib/workflow/node-catalog.ts:1166`, `frontend/components/flow/inspector.tsx:1583` -- sink catalog and secret-free target editor.
- `backend/workflow/gaojixing_certification.py:112` -- read-only certified projection contract.

## Tasks & Acceptance

**Execution:**
- [x] `backend/models/delivery_connection.py`, `backend/schemas/delivery_connection.py`, `backend/migrations/versions/d1e2f3a4b5c6_add_delivery_connections.py` -- add encrypted connection metadata and idempotent attempt storage.
- [x] `backend/services/feishu_bitable_delivery.py`, `backend/api/v1/delivery_connections.py`, `backend/api/v1/__init__.py` -- implement fixed-host Feishu auth/write client and redacted CRUD/probe API.
- [x] `backend/workflow/runtime_registry.py`, `backend/workflow/opencli_hda_tracer.py`, `backend/workflow/block_reasons.py` -- bind and execute a REAL Feishu sink from stored Record refs with typed failures.
- [x] `frontend/components/providers/feishu-bitable-connection-panel.tsx`, provider catalog, and `frontend/lib/api/{types,endpoints,hooks}.ts` -- configure/test reusable connections without secret readback.
- [x] `frontend/components/flow/feishu-bitable-target-editor.tsx`, `frontend/lib/workflow/node-catalog.ts`, and Inspector integration -- select connection/app/table/mapping in the workflow without embedding credentials.
- [x] Backend integration/unit tests and `frontend/scripts/check-feishu-bitable-regressions.mjs` -- cover the matrix, migration head, secret redaction, idempotency, catalog and Inspector contracts.

**Acceptance Criteria:**
- Given a configured connection and a stored certified Record, when the Feishu sink completes, then exactly one Bitable row and one successful local attempt reference the same connection, target, run, Record and evidence digests.
- Given any API response, workflow trace, log, or frontend state, when inspected after configuration and delivery, then neither app secret nor tenant access token is present.
- Given a published run retry or resume, when the same Record reaches the same Feishu target, then the workflow reports the existing successful delivery without creating a duplicate row.
- Given no Feishu connection, when operators use existing Gaojixing workflows, then local certification and Record persistence continue unchanged.

## Spec Change Log

## Design Notes

The connection owns tenant app credentials; the workflow owns the target. Canonical Record keys map through a non-secret field map. Operators grant the app edit access to an existing Bitable and provide its app/table IDs; provisioning is excluded.

## Verification

**Commands:**
- `uv run --extra dev pytest -q --no-cov tests/unit/test_feishu_bitable_delivery.py tests/integration/test_delivery_connections_api.py tests/integration/test_workflow_gaojixing_hda.py tests/unit/test_migration_heads.py` -- connection, delivery, idempotency, trace, and schema contracts pass.
- `uv run ruff check backend tests` -- changed Python passes lint.
- `node --test frontend/scripts/check-feishu-bitable-regressions.mjs` -- settings and workflow UI contracts pass.
- `pnpm --dir frontend exec tsc --noEmit` -- frontend types compile.

**Manual checks (if no live credentials):**
- Inspect API responses, trace samples, database ciphertext, and rendered node JSON; secret/token values are absent and existing Gaojixing flows remain runnable.

**Fresh results (2026-08-25):**
- Valid connection: CRUD, sparse PATCH preservation, explicit-null rejection, ciphertext storage, and missing-key 503 are covered.
- Target validation: official fixed host, bearer request, successful field count, typed failure, target-ID validation, and response redaction are covered without live credentials.
- Certified delivery: a workflow-level stored Record path creates successful local attempts and emits a redacted delivery trace; forged generic source provenance is rejected by the runtime trust boundary.
- Retry/resume: successful attempts are reused; pending claims do not resend; failed attempts are durably observable and safely retryable; idempotency conflicts fail closed.
- Missing configuration: disabled connections and missing external-mutation permission block before any outbound call.
- Backend focused suite: `35 passed`; changed-file Ruff: passed.
- Frontend regression suite: `3 passed`; normal `check:workflow-regressions`: `81 passed`; TypeScript: passed.
- Repository-wide Ruff remains blocked by unrelated baseline debt recorded in `deferred-work.md`.

## Suggested Review Order

**Delivery trust boundary**

- Start with certified Record verification, mapping safety, permission gating, and trace output.
  [`opencli_hda_tracer.py:3802`](../../backend/workflow/opencli_hda_tracer.py#L3802)

- Review durable claims, redacted Feishu failures, and retry/idempotency behavior.
  [`feishu_bitable_delivery.py:107`](../../backend/services/feishu_bitable_delivery.py#L107)

- Confirm the node binds only saved connection and non-secret target references.
  [`runtime_registry.py:724`](../../backend/workflow/runtime_registry.py#L724)

**Connection and audit storage**

- Inspect encrypted credential ownership and immutable delivery-attempt history.
  [`delivery_connection.py:12`](../../backend/models/delivery_connection.py#L12)

- Check masked CRUD, target probing, history-preserving update and delete guards.
  [`delivery_connections.py:17`](../../backend/api/v1/delivery_connections.py#L17)

- Verify the single-head migration and idempotency indexes.
  [`d1e2f3a4b5c6_add_delivery_connections.py:16`](../../backend/migrations/versions/d1e2f3a4b5c6_add_delivery_connections.py#L16)

**Workflow authoring and settings**

- Review reusable connection management under Provider 与连接.
  [`feishu-bitable-connection-panel.tsx:128`](../../frontend/components/providers/feishu-bitable-connection-panel.tsx#L128)

- Review secret-free target selection and identity-preserving field mapping.
  [`feishu-bitable-target-editor.tsx:18`](../../frontend/components/flow/feishu-bitable-target-editor.tsx#L18)

- Confirm the typed sink catalog defaults and discoverability.
  [`node-catalog.ts:1180`](../../frontend/lib/workflow/node-catalog.ts#L1180)

**Verification**

- Follow the workflow-level certified delivery, failure, permission, and redaction coverage.
  [`test_workflow_gaojixing_hda.py:308`](../../tests/integration/test_workflow_gaojixing_hda.py#L308)

- Check fixed-host, probe, durable-failure, and idempotency unit coverage.
  [`test_feishu_bitable_delivery.py:48`](../../tests/unit/test_feishu_bitable_delivery.py#L48)

- Check masked CRUD, sparse update, encryption failure, and probe redaction coverage.
  [`test_delivery_connections_api.py:11`](../../tests/integration/test_delivery_connections_api.py#L11)
