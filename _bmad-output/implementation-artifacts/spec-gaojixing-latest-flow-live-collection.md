---
title: 'Run Gaojixing Live Collection Through the Latest Workflow'
type: 'bugfix'
created: '2026-08-24'
status: 'in-progress'
review_loop_iteration: 0
baseline_commit: 'f0390d4c4c1029347255b0eb94112ba1b00b998c'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The deployed Gaojixing runtime is not traceable to the latest branch: four recent runs used the wrong trigger path, one could not bind the certified browser, and the only real run stopped after 38 of 723 questions when Doubao exposed no recommended-follow-up chips. Captured evidence is stored in the archive but is not materialized as project Records, so downstream agents cannot consume it through the normal data surface.

**Approach:** Make the repository-owned published workflow, job claimant, certified Doubao driver, evidence contract, and project data sink operate as one versioned path. Prove the path with a one-question live canary before any full question-bank run.

## Boundaries & Constraints

**Always:** Use the immutable published workflow endpoint and resume the same WorkflowRun after collection; deploy API, claimant, browser tooling, and schema from one identifiable commit; preserve raw response, formal chat URL, copied share URL, screenshots, digests, checkpoints, and lineage; represent genuinely absent optional UI modules explicitly rather than inventing evidence; keep credentials and browser-session details out of logs and artifacts; retain captcha reconciliation without resubmitting the question.

**Ask First:** Running the 723-question bank; weakening any core answer, URL, screenshot, digest, or source-chain requirement; changing credentials or external Hermes schedules; destructive cleanup of existing runs, archives, or records.

**Never:** Use the legacy direct-run endpoint to imitate the published schedule graph; accept fixture-only or preflight-only success; report completion while the job is merely queued; fabricate recommended follow-ups; mix host scripts, images, or source files from different revisions; include the unrelated project-portability or Agent Home work.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Live canary | Published workflow plus a staged `B001` ecommerce-oriented JSON question bank and authenticated Doubao CDP session | One durable job is claimed, one question is captured and certified, the same run completes, and an agent-consumable Record links to the archive evidence | Fail closed with a typed, actionable reason and retain resumable state |
| No follow-up chips | Stable answer page has core evidence but Doubao renders no recommendation module | Capture records an explicit absence; core evidence can still pass without fabricated fields | Fail only if the module is present but extraction is inconsistent, or another core field is missing |
| Captcha or ambiguity | Verification challenge, unstable page, or uncertain chat binding | Job enters waiting reconciliation and preserves the current checkpoint | Resume the same run after human verification; never ask the question twice |
| Claimant unavailable | API queues a job but no compatible worker claims it | Readiness/health identifies the claimant failure before the canary is accepted | Do not treat Hermes gateway liveness or a queued event as success |

</frozen-after-approval>

## Code Map

- `backend/api/v1/studio_workflows.py` -- published multipart question-bank entry and same-run resume boundary.
- `backend/workflow/gaojixing_worker_runtime.py` -- executor dispatch and repository-owned job execution contract.
- `backend/workflow/gaojixing_collection_runner.py` -- durable lease, per-question checkpoints, reconciliation, and finalization.
- `backend/workflow/gaojixing_doubao_driver.py` -- OpenCLI/CDP collection and page-evidence extraction.
- `backend/workflow/gaojixing_doubao.py` -- question-bank parsing and evidence audit semantics.
- `backend/workflow/opencli_hda_tracer.py` -- four-node execution, certification, delivery, and Record/lineage persistence.
- `backend/workflow/gaojixing_archive.py` -- immutable raw evidence and archive manifests.
- `docker-compose.yml` and `.env.example` -- reproducible API, claimant, browser, storage, and version configuration.
- `frontend/lib/workflow/gaojixing-doubao-workflow.ts` -- canonical four-node published graph and upload contract.
- `tests/integration/test_workflow_gaojixing_hda.py`, `tests/unit/test_gaojixing_collection_service.py`, `tests/unit/test_gaojixing_doubao_driver.py`, `tests/unit/test_gaojixing_workflow_tools.py`, `frontend/scripts/check-gaojixing-doubao-workflow.mjs` -- targeted regression surfaces.

## Tasks & Acceptance

**Execution:**
- [ ] `docker-compose.yml`, `.env.example`, and runtime startup code -- make the claimant and browser dependencies repository-owned, health-checkable, and revision-identifiable.
- [ ] Published-run API and Gaojixing runtime modules -- keep one durable run from upload through claim, capture, certification, delivery, and typed failure/reconciliation.
- [ ] Driver and evidence audit modules -- distinguish absent optional recommendation UI from broken extraction without weakening core evidence.
- [ ] HDA tracer/data persistence -- materialize each certified question as a project Record with links and digests that preserve the raw evidence chain.
- [ ] Targeted backend/frontend tests -- cover the matrix, trigger routing, claimant readiness, same-run resume, and Record lineage.
- [ ] Live environment -- rebuild from this branch and execute one `B001` ecommerce canary through the published endpoint.

**Acceptance Criteria:**
- Given the deployed revision and a valid one-question bank, when the published workflow starts, then trace state progresses from waiting through a claimed collection job to certified workflow completion on the same run ID.
- Given a certified capture, when project data is queried, then at least one Record for that run exposes the answer and traceable links/digests to raw JSON, formal chat/share URLs, and distinct top/answer/bottom screenshots.
- Given a page with no recommendation module, when evidence is audited, then absence is recorded truthfully and does not alone abort the batch; missing core evidence still fails closed.
- Given the canary result, when runtime identity is inspected, then API and claimant report the branch commit and no deployed Gaojixing module differs from it.

## Spec Change Log

## Design Notes

The canary question bank is `{"phase1":[],"phase2":[{"id":"B001","question":"高吉星藻油 DHA 孕妇款在哪里可以买到？请列出官方旗舰店、京东或天猫的在售规格、价格区间和可访问的商品链接。"}]}`. A successful canary authorizes no automatic expansion to the full bank. Archive files remain the immutable evidence source; the project Record is an indexed, agent-facing projection with provenance, not a second editable copy.

## Verification

**Commands:**
- `uv run --extra dev pytest -q tests/integration/test_workflow_gaojixing_hda.py tests/unit/test_gaojixing_collection_service.py tests/unit/test_gaojixing_doubao_driver.py tests/unit/test_gaojixing_workflow_tools.py` -- targeted backend contracts pass.
- `pnpm --dir frontend install --frozen-lockfile && node --test frontend/scripts/check-gaojixing-doubao-workflow.mjs` -- frontend graph and multipart contracts pass.
- `docker compose config` -- deployment topology resolves without machine-specific source overlays.

**Manual checks (if no CLI):**
- Inspect the canary trace, collection checkpoint, archive manifest/files, and project Record; all share the same run ID and evidence digests, and the deployed revision equals this branch commit.
