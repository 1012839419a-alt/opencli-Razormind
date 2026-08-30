---
title: 'GitHub #36: Isolated Non-Bypass Happy Vertical Proof'
type: 'chore'
created: '2026-08-30'
status: 'done'
baseline_commit: 'fb78d35507f91fca568fc8e0511a3c5064b1f7bb'
context: ['.claude/CLAUDE.md', 'docs/wayfinder/iii-vertical/non-bypass-iii-vertical-spec.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** #29–#35 have focused tests, but no fresh isolated container run proves the complete Admin → III → collector → ODP → manifest → graph → receiver route without mistaking a mock, projection, fallback, or 2xx for evidence.

**Approach:** Add one acceptance-only, disposable Compose topology and one real-network runner. Existing Admin, III workers, Rust ODP, and v2 receiver code remain live; a deterministic `OPENCLI_BIN` supplies source data only.

## Boundaries & Constraints

**Always:** Pin engine/CLI to `iiidev/iii:0.19.4@sha256:14ed48b463d8a2e0d3583512acf106b3514f406c5e9965a5854710ff936e1e86` (linux/amd64; local `/app/iii` is `0.19.4`). Harness target copies it to `/opt/iii/iii`, build-checks version, sets `III_CLI_PATH=/opt/iii/iii`, `III_URL=ws://proof-iii:49134`; those checks plus one Admin submit producing lifecycle evidence are admission.

Per-run Admin: `DATABASE_URL`, `REDIS_URL=redis://proof-redis:6379/0`, `ODP_QUERY_URL`, `ODP_QUERY_ADMIN_CREDENTIAL`, `III_LIFECYCLE_URL/TOKEN`, `III_INGRESS_RECEIPT_SECRET`, `API_AUTH_TOKEN`. ODP: `ODP_REDIS_URL=redis://proof-redis:6379/2`, `ODP_DATABASE_URL`, `ODP_QUERY_DATABASE_URL`, `ODP_QUERY_ADMIN_CREDENTIAL`, `ODP_QUERY_CURSOR_SECRET`, `ODP_INGRESS_RECEIPT_SECRET`. Collector/bridge: `III_URL`, `ADMIN_III_LIFECYCLE_URL/TOKEN`, `API_AUTH_TOKEN`; generated values are never captured.

Admin joins III, query, callback, driver, OIDC, receiver—not worker/ingest/store. A dual-network relay alone forwards three fixed callback paths plus bridge token. Receiver app/PostgreSQL is `8.8.8.8`/`proof-controlled-receiver` on internal `8.8.8.0/24`, with per-run CA/SAN, Admin trust, registry, distinct request/inbound/receipt keys.

Seed only matching Studio/RBAC workspace, `proof-proposer` operator, and `proof-reviewer` maintainer; local JWKS issues RS256 tokens. All flow facts are API-only. Assume scoped materialization GET returns `researchGraphManifestRef`; submit it unchanged, never read DB/recompute it.

**Ask First:** Changing #29–#35 contracts, default Compose, authority/retry policy, or using external destination, user credential, or host port.

**Never:** Reuse normal/shared/staging/production resources; monkeypatch III/HTTP/receiver; accept public webhook, Admin fallback, projection-only fact, or bare 2xx; retain secrets or private transport data. Terminal proof is `DeliveryExecution.final_outcome`, verified classification, and signed receipt—not `ControlledAcceptanceBusinessOutcomeV1`. #37 owns retention/expiry, authenticated/audited access, key lifecycle, failure orchestration; #36 emits only ephemeral signed redacted happy evidence.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Fresh route | Empty labeled project; fixture/services admitted | Correlated chain ending in `DeliveryExecution.final_outcome=accepted` | No signature before facts validate |
| Substitute/teardown | Forbidden source or terminal path | No certificate; redacted bundle may survive | Pre-sign reject; ledger cleanup removes only created resources |

</frozen-after-approval>

## Code Map

- `Dockerfile`, `docker-compose.yml`, `backend/workflow/iii_collection_dispatch.py` — CLI trigger.
- `iii/lib/opencli_cli.py`, worker sources, `odp-rs/crates/` — live chain.
- `backend/security/identity.py`, `workspace_rbac.py`, `controlled_receiver.py` — scope/receiver.

## Tasks & Acceptance

**Execution:**
- [x] `Dockerfile`, `docker-compose.non-bypass-acceptance.yml`, `tests/acceptance/fixtures/opencli-proof{,.sha256}` — add the isolated no-port services. Fixture accepts only `bilibili search --help` and `bilibili search --keyword vertical-proof -f json`, verifies committed SHA-256, emits one canonical item, otherwise fails.
- [x] `tests/acceptance/non_bypass_vertical.py` — create 0700 scratch/ledger/secrets, seed setup identities/workspace, admit image/CLI/health/network, drive APIs, and validate IDs/hashes through `final_outcome`, verified classification, receiver receipt.
- [x] `scripts/run_non_bypass_happy_vertical.py`, `tests/acceptance/test_non_bypass_happy_vertical.py` — allowlist canonical JSON keys `schemaVersion,run,image,topology,command,attempt,lifecycleHashes,reportHash,ingressReceiptHash,researchGraphManifestRef,pin,decision,execution,receiverReceipt,redactionProfile`; reject other keys/secrets and five substitutions before detached Ed25519 signature/public key; label-scoped `finally` runs `down --volumes` and leak checks.

**Acceptance Criteria:**
- Given a new run, when admission completes, then pinned engine/CLI, `III_CLI_PATH`, `III_URL`, fixture digest, relay, and topology are proven.
- Given its item, when APIs drive the route, then intent, III, report, signed ingress, manifest ref, pin, decision, signed receipt, and `final_outcome=accepted` share IDs/hashes.
- Given forbidden or unsafe proof input, when pre-sign validation runs, then no signature is written.
- Given any terminal path, when cleanup ends, then only ledger-labeled resources/0700 secrets are gone; the ephemeral redacted bundle, signature, public key remain.

## Spec Change Log

## Design Notes

Fixture is source-only: subprocess, III, bridge, ODP, callback, receiver live. The internal public-looking subnet retains #35 SSRF/DNS-pinning without egress; #36 evidence, not #37 certification.

## Verification

**Commands:**
- `docker build --target non-bypass-acceptance -t non-bypass-admin:local .` — expected: copied `/opt/iii/iii --version` is exactly `0.19.4`.
- `docker compose -p non-bypass-preflight -f docker-compose.non-bypass-acceptance.yml config --quiet` — expected: pinned images; no ports/default resources; declared networks.
- `uv run --extra dev python scripts/run_non_bypass_happy_vertical.py --artifact-dir .artifacts/non-bypass-vertical` — expected: fresh signed redacted happy artifact and zero labeled resource leaks.
- `uv run --extra dev pytest -o addopts='' tests/acceptance/test_non_bypass_happy_vertical.py -q` — expected: live route and every pre-sign substitution rejection pass.

**Completed evidence (2026-08-30):**
- Baseline: `fb78d355`; implementation commits: `f364555c`, `0d2e01a6`, and `f207e5eb`.
- `docker build --target non-bypass-acceptance -t non-bypass-admin:local .` passed; `/opt/iii/iii --version` reported `0.19.4`.
- `docker compose -p non-bypass-preflight -f docker-compose.non-bypass-acceptance.yml config --quiet` passed.
- `uv run --extra dev pytest -o addopts='' tests/acceptance/test_non_bypass_happy_vertical.py -q` passed: `13 passed`; its unskipped live test verifies the signed artifact and labeled-resource cleanup.
- `uv run --extra dev python scripts/run_non_bypass_happy_vertical.py --artifact-dir .artifacts/non-bypass-vertical` passed; artifact `nbv-9f714ddeef0b4e99ad90d7d4bcd11e1b` records `outcome=accepted` and a verified durable receiver receipt.
- Focused III, materialization, and delivery regressions passed: `52 passed, 1 skipped`.
- Sentrux passed with no structural degradation (`1495 -> 1495`).
- Final independent review at shared HEAD `f207e5eb`: `PASS`, with zero P0/P1/material P2 findings.
- Integration re-verification at `3c0d847b` after merge `d4f5b03e` passed: `15 passed` in 146.53s. The unskipped live runner verified the new canonical collection/materialization-to-delivery binding, detached signature, and zero labeled-resource leaks.

## Suggested Review Order

**Isolated runtime boundary**

- Establishes the disposable, no-host-port proof topology before inspecting application behavior.
  [`docker-compose.non-bypass-acceptance.yml:1`](../../docker-compose.non-bypass-acceptance.yml#L1)

- Copies the pinned III binary into the acceptance image's enforced CLI location.
  [`Dockerfile:70`](../../Dockerfile#L70)

**End-to-end proof orchestration**

- Coordinates admission, live execution, validation, signing, and label-scoped cleanup in one run.
  [`run_non_bypass_happy_vertical.py:447`](../../scripts/run_non_bypass_happy_vertical.py#L447)

- Drives real scoped APIs and emits the correlated redacted evidence DTO.
  [`non_bypass_vertical.py:102`](../../tests/acceptance/non_bypass_vertical.py#L102)

**Non-bypass terminal evidence**

- Fail-closes the allowlisted evidence against topology, manifest, decision, execution, and receipt bindings.
  [`non_bypass_proof_contract.py:56`](../../scripts/non_bypass_proof_contract.py#L56)

- Records only terminal accepted/rejected delivery outcomes after a durable receiver result.
  [`delivery_execution.py:497`](../../backend/workflow/delivery_execution.py#L497)

- Verifies receiver receipts bind identity and immutable delivery facts before classification.
  [`controlled_receiver.py:285`](../../backend/security/controlled_receiver.py#L285)

**Verification perimeter**

- Pins the source-only fixture and proves unsupported invocations fail.
  [`test_non_bypass_happy_vertical.py:96`](../../tests/acceptance/test_non_bypass_happy_vertical.py#L96)

- Exercises each prohibited provenance substitute and stale or mismatched receipt attempt.
  [`test_non_bypass_happy_vertical.py:143`](../../tests/acceptance/test_non_bypass_happy_vertical.py#L143)

- Independently verifies the emitted signature and cleanup of all labeled resources.
  [`test_non_bypass_happy_vertical.py:210`](../../tests/acceptance/test_non_bypass_happy_vertical.py#L210)
