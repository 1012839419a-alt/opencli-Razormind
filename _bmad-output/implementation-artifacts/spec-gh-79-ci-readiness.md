---
title: 'Restore PR 79 CI Readiness'
type: 'bugfix'
created: '2026-08-25'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd2f81922179e60be608cac8d2d685b80b0aace42'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** PR #79 is mergeable but its CI is red because cumulative local-first work left browser smoke, public Compose, capability-governance, migration compatibility, and PostgreSQL concurrency checks out of sync or unsafe.

**Approach:** Repair each demonstrated root cause with the smallest production-safe change, reproduce the failing gates locally, push the fixes to the existing PR branch, and require the rerun to finish green.

## Boundaries & Constraints

**Always:** Preserve local-first authentication, Gaojixing browser behavior, Feishu delivery trust boundaries, migration reversibility, public image portability, and gap-free per-Run event sequences. Keep fixes independently testable and derived from the failed CI evidence.

**Ask First:** Rewriting published branch history, closing or replacing PR #79, weakening a security or data-integrity invariant, or merging the PR.

**Never:** Skip or disable failing tests; mark flaky failures as allowed; remove Gaojixing or Feishu behavior merely to reduce the diff; expose secrets; replace concurrency correctness with process-local locking.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Login smoke | Frontend runs without a backend | Test controls local-auth status and verifies the current password form | Backend absence does not make the assertion nondeterministic |
| Public stack | Fresh Linux checkout and Compose build override | API, frontend, and browser agent start healthy | Mounted entrypoint is executable and public image names remain portable |
| Concurrent events | Two PostgreSQL transactions append to one Run from different sessions | Both commit with sequences 1 and 2 | No deadlock, duplicate, or sequence gap |
| Legacy database | Older Alembic revision upgrades to head | Schema and revision reach the current single head | Repair migrations remain effective |

</frozen-after-approval>

## Code Map

- `frontend/e2e/login.spec.mjs` -- stale token-field smoke assertion; local auth status must be controlled before checking the current UI.
- `frontend/playwright.config.mjs` -- production-server smoke harness; CI intentionally runs without the backend service.
- `docker-compose.yml` -- public image contract and Gaojixing bind mounts used by release smoke.
- `chrome-extra/entrypoint.sh` -- mounted browser entrypoint currently committed without executable mode.
- `backend/workflow/workflow_run_events.py:_lock_run_event_allocator` -- PostgreSQL row-lock upgrade deadlocks after pending FK rows flush.
- `tests/integration/test_intelligence_session_store.py:test_two_sessions_share_gap_free_workflow_event_allocator` -- exact PostgreSQL concurrency regression.
- `docs/backend-capability-exposure-matrix.yaml` -- missing 15 new OpenAPI operations and stale wrapper-reference classification.
- `tests/integration/test_legacy_{native_intelligence,plugin}_migration.py` -- hard-coded pre-Feishu Alembic head.
- `tests/unit/test_public_release_contract.py` and `.github/workflows/ci.yml` -- authoritative release and CI gates.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/e2e/login.spec.mjs` -- mock the local-auth status and assert the current administrator setup/login controls.
- [x] `docker-compose.yml`, `chrome-extra/entrypoint.sh` -- restore portable image naming and executable startup while retaining Gaojixing mounts.
- [x] `backend/workflow/workflow_run_events.py` -- serialize PostgreSQL allocation without row-lock upgrade deadlocks; retain SQLite behavior.
- [x] `docs/backend-capability-exposure-matrix.yaml` -- reconcile new operations and wrapper decisions with actual OpenAPI/frontend usage.
- [x] Legacy migration tests -- resolve the expected revision from the current Alembic head instead of freezing an obsolete revision.
- [x] Run focused gates and CI-equivalent suites locally; pushing and remote rerun inspection follow the review gate.

**Acceptance Criteria:**
- Given PR #79 at the updated head, when GitHub CI completes, then every required check reports success without ignored failures.
- Given two concurrent PostgreSQL intelligence sessions sharing one Workflow Run, when both emit events, then both transactions commit and the persisted sequences are gap-free.
- Given the public Compose files on Linux, when the release stack starts from a fresh checkout, then all requested services become healthy.

## Spec Change Log

## Design Notes

Use a transaction-scoped PostgreSQL advisory lock keyed by Run ID before sequence reservation. It serializes only writers for the same Run and avoids upgrading FK key-share locks to `FOR UPDATE`; SQLite retains its existing write-lock path.

## Verification

**Commands:**
- `pnpm --dir frontend build && pnpm --dir frontend test:smoke` -- current login smoke passes without a backend.
- `uv run pytest -q --no-cov tests/unit/test_capability_exposure_matrix.py tests/unit/test_public_release_contract.py tests/integration/test_legacy_native_intelligence_migration.py tests/integration/test_legacy_plugin_migration.py` -- governance, release, and legacy upgrade checks pass.
- PostgreSQL conformance command from `.github/workflows/ci.yml` -- all marked tests pass, including the shared allocator case.
- Release Compose command from `.github/workflows/ci.yml` -- API, frontend, and agent become healthy.
- `git diff --check` -- clean patch formatting.

**Fresh results (2026-08-25):** production frontend build passed; both local-admin login states passed isolated browser smoke (`2 passed`); public Compose build and all three service health checks passed; final PostgreSQL allocator and intelligence-store conformance passed (`28 passed`), following the earlier full conformance run (`37 passed`); focused governance/release/legacy/event suite passed (`20 passed`); Feishu/auth/migration suite passed (`45 passed`); workflow regressions passed (`81 passed`); Ruff, ESLint (one pre-existing warning), generated catalog check, Compose validation, and `git diff --check` passed.

## Suggested Review Order

**Concurrency integrity**

- Serialize same-run writers without PostgreSQL row-lock upgrades or 32-bit hash collisions.
  [`workflow_run_events.py:280`](../../backend/workflow/workflow_run_events.py#L280)

- Pin the advisory-lock contract with dialect-specific SQL verification.
  [`test_workflow_run_events.py:339`](../../tests/unit/test_workflow_run_events.py#L339)

**Public deployment**

- Pull coherent published images while reserving builds for the explicit override.
  [`docker-compose.yml:147`](../../docker-compose.yml#L147)

- Execute the bind-mounted browser entrypoint safely in the public stack.
  [`docker-compose.yml:332`](../../docker-compose.yml#L332)

- Guard the executable-bit contract before the release smoke starts.
  [`ci.yml:113`](../../.github/workflows/ci.yml#L113)

**Capability governance**

- Model Feishu delivery as its own provider capability and node sink.
  [`backend-capability-exposure-matrix.yaml:184`](../../docs/backend-capability-exposure-matrix.yaml#L184)

- Bind delivery operations to the Feishu provider instead of Dify components.
  [`backend-capability-exposure-matrix.yaml:2408`](../../docs/backend-capability-exposure-matrix.yaml#L2408)

**Deterministic smoke and migration gates**

- Validate isolated Playwright ports before interpolating the server command.
  [`playwright.config.mjs:3`](../../frontend/playwright.config.mjs#L3)

- Cover both first-run setup and returning local-admin login states.
  [`login.spec.mjs:14`](../../frontend/e2e/login.spec.mjs#L14)

- Resolve legacy upgrade expectations from the repository's current Alembic head.
  [`test_legacy_native_intelligence_migration.py:15`](../../tests/integration/test_legacy_native_intelligence_migration.py#L15)
