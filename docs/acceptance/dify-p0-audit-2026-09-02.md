# Dify P0 lifecycle audit

Audit date: 2026-09-02

Audited revision: `02342ae3cbeb642a0e2d032aec45f92b695339a0`

Parent scope: `docs/dify-p0-compatibility-runtime-PRD.md` and the issue pack in
`docs/dify-p0-compatibility-runtime-issues/`. GitHub issue #15 could not be
read from this environment: `gh issue view 15 --repo 2233admin/opencli-admin
--comments` failed before receiving a response because the configured proxy
`127.0.0.1:7897` refused the connection. This record therefore does not infer
additional issue scope beyond the repository-local parent PRD.

## Decision

Do **not** close issue #15 or mark the Dify P0 parent complete. The repository
contains the import, managed compile, plugin metadata, event projection, and
frontend wiring implementation, and the deterministic local checks below pass.
The end-to-end lifecycle is still only partially evidenced because deployment,
restart, configured-provider, allowed-network, and browser-capture gates remain
open.

## Acceptance matrix

| PRD acceptance | Current evidence | Honest state |
|---|---|---|
| Pure-logic DSL imports as one managed package | `tests/integration/test_workflow_dify_import_api.py::test_import_returns_one_managed_package_and_preserves_source_ids`; `frontend/scripts/check-dify-p0-regressions.mjs` | Evidenced |
| Compile emits one `workflow.compat.dify.graphon` binding and does not flatten internals | `tests/integration/test_workflow_dify_compile_api.py::test_compile_emits_one_graphon_binding_without_flattening_internals` | Evidenced |
| Pinned Graphon execution emits ordered nested events | `tests/integration/test_workflow_dify_run.py::test_managed_dify_run_persists_nested_graphon_events`; `compat/dify_graphon_runtime/tests/test_contract.py` | Partially evidenced: deterministic fake-client and sidecar contract coverage pass, but no current-HEAD container run |
| Projection survives API process restart or database reload | `tests/integration/test_workflow_dify_event_replay.py::test_dify_projection_and_events_reload_from_a_fresh_database_session` clears `_RUNS`, closes the first client/session, and compares a fresh-session projection and replay | Partially evidenced: durable database reload is now covered; a real API process restart against a persisted deployment database remains open |
| LLM either completes with configured provider/Slim or returns exact blockers | compile/import tests cover `dify_model_provider_required` and `dify_slim_runtime_required` | Partially evidenced: no configured provider plus pinned Slim success run was available |
| HTTP is blocked without permission and succeeds with permission plus allowed domain | `test_compile_projects_graphon_blockers_with_stable_codes` covers blocked HTTP; sidecar policy test covers `network_adapter_required` when network is enabled | Partially evidenced: no allowed-domain Dify HTTP success run against a local fixture server |
| Code node returns `dify_sandbox_required` | `tests/integration/test_workflow_dify_compile_api.py`; `compat/dify_graphon_runtime/tests/test_contract.py` | Evidenced |
| Manifest and `.difypkg` install through plugin catalog | `tests/integration/test_plugin_dify_import_api.py` | Evidenced |
| Malicious, oversized, invalid, and duplicate packages are rejected | `tests/unit/test_dify_package_security.py`; API tests cover invalid YAML, missing fields, and version conflict | Partially evidenced: focused parser security and representative API mappings pass, but no current deployment upload run |
| Unsupported plugin capabilities remain `BLOCKED` | `test_manifest_import_persists_blocked_capabilities_and_lists` and backend catalog projection | Evidenced |
| Plugin page is backend-backed and Studio exposes locked projected definitions | `frontend/scripts/check-dify-p0-regressions.mjs` | Evidenced at source/regression level; browser screenshots are absent |
| Existing workflow/run/EvidenceBatch/control-plane regressions remain green | Fresh commands below | Partially evidenced: Dify-specific and workflow/EvidenceBatch suites pass; the combined control-plane suite has two unrelated baseline failures |

## Fresh verification at audited revision

All commands were run from the repository root on the audited revision.

| Command | Result |
|---|---|
| `uv run --offline pytest --no-cov tests/integration/test_workflow_dify_import_api.py tests/integration/test_workflow_dify_compile_api.py tests/integration/test_workflow_dify_run.py tests/integration/test_workflow_dify_event_replay.py tests/integration/test_plugin_dify_import_api.py tests/unit/test_dify_package_security.py -q` | **45 passed** |
| `uv run --offline pytest --no-cov tests/unit/test_workflow_http_source_executor.py tests/unit/test_workflow_rss_source_executor.py -q` | **6 passed** |
| `uv run --offline pytest --no-cov tests/integration/test_workflow_dify_event_replay.py -q` | **1 passed** |
| `uv run --offline pytest --no-cov tests/integration/test_workflow_compile_api.py tests/integration/test_workflow_conformance.py tests/integration/test_workflow_evidence_batches_api.py tests/integration/test_workflow_opencli_hda_trace_api.py tests/unit/test_workflow_node_paths.py -q` | **101 passed** |
| `npm --prefix frontend run check:dify-p0` | **8 passed** |
| `npm --prefix frontend run check:workflow-regressions` | **51 passed, 9 unrelated baseline failures** |
| `npm --prefix frontend run check:control-plane` | **19 passed, 2 unrelated baseline failures** |
| `.\.venv\Scripts\ruff.exe check compat/dify_graphon_runtime --output-format concise` | **clean** |
| `git diff --check` | **clean** |

The frontend checks require the locked dependencies from `frontend/pnpm-lock`;
they were installed from the local pnpm store with
`pnpm --dir frontend install --offline --frozen-lockfile`. No lockfile or
tracked dependency file changed.

The 9 workflow-regression failures and 2 control-plane failures are not Dify
P0 failures. They are existing repository-wide contract drift failures in
unrelated OpenCLI adapter, navigation, and selector expectations; the failing
workflow assertions that invoke Python also report missing dependencies when
run outside the project virtualenv. They are not used as evidence to close or
reopen Dify scope.

## Environment blockers

1. `docker info` succeeds, but `docker compose --profile dify build
   dify-graphon-runtime` cannot fetch `python:3.13-slim-bookworm`; Docker is
   configured to use `127.0.0.1:7897`, which actively refuses registry
   connections. No sidecar image was built or started in this audit.
2. `uv run --project compat/dify_graphon_runtime pytest ...` cannot fetch the
   pinned Graphon Git revision for the same network reason. The sidecar tests
   therefore were not rerun at this revision; the historical record reports
   19 passed at the earlier local-process acceptance.
3. No configured OpenAI-compatible provider plus executable Dify Slim helper
   was available. The implementation correctly keeps the LLM fixture blocked
   rather than producing mock output.
4. No local fixture-server acceptance run demonstrated a Dify HTTP node with
   both network permission and an allowed domain. The current sidecar contract
   deliberately reports `network_adapter_required` when network is enabled
   without an installed network-policy adapter.
5. The existing acceptance record has no committed Plugin Center or Studio
   screenshots. Browser source/regression checks pass, but visual evidence is
   not recorded.

## Follow-up blockers

Keep the parent open and track these as child work against the existing issue
pack rather than claiming completion:

- P0-01/P0-06 deployment gate: build and run the pinned sidecar through Compose,
  capture `/health`, and verify container restart behavior.
- P0-04 persistence gate: run the API and sidecar with a durable test database,
  restart the API process, then compare nested projection and replay payloads.
- P0-04 runtime matrix: add a real allowed-domain HTTP fixture-server run and a
  configured provider/Slim LLM run, or keep both explicitly blocked.
- P0-06 browser gate: capture and commit the plugin list/detail and Studio
  locked-node/import screenshots at the documented desktop and narrow widths.

Until those gates have fresh evidence, the truthful parent state is
**implemented with deterministic local coverage, not lifecycle-complete**.
