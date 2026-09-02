# Frontend Regression Test Plan

## BMAD QA activation and scope

- Workflow: `bmad-qa-generate-e2e-tests`, activated under OMP 5.6 Luna.
- Discovery mode: Workflow Step 1 auto-discover features (no single component supplied).
- Activation resolution: `resolve_customization.py --skill bmad-qa-generate-e2e-tests --key workflow` completed successfully. Prepend and append activation steps were empty. Persistent fact glob `**/project-context.md` was checked; no files were present.
- Config: project `snailfish`; communication/output language English; implementation artifacts resolve to `_bmad-output/implementation-artifacts`.
- This is preparation only: no product or test source is changed and no tests are run.
- Explicit non-scope: do not invent tests for future geoXI/OODA contracts; targets below are observable in the current UI.

## Framework and repository conventions

The frontend is Next.js/React with Playwright available as `@playwright/test` (frontend/package.json). `frontend/playwright.config.mjs` uses Chromium, `http://127.0.0.1:3000`, and starts the production app with `pnpm start --hostname 127.0.0.1 --port 3000`. The configured E2E directory is `frontend/e2e`; currently it contains only `login.spec.mjs`.

The frontend has no Jest/Vitest/Cypress dependency. Existing unit/contract-style regression coverage is Node's built-in `node:test`, invoked by scripts such as `check:workflow-regressions`, `check:node-capabilities`, `check:control-plane`, `check:opencli-business-workflows`, and related scripts. These tests mostly inspect/import TypeScript source and data contracts rather than driving a browser. CI (`.github/workflows/ci.yml`) runs lint, TypeScript, workflow regressions, build, then Playwright browser smoke (`pnpm test:smoke`) in the frontend job; the dedicated workflow-check job runs contract scripts. New browser tests should therefore use Playwright in `frontend/e2e`, while deterministic projection/validation logic can remain Node `node:test`.

## Current user surfaces and observed coverage

- `/plugins` exposes installed plugin, node capability, and marketplace tabs; provider state/readiness labels and detail sheets are implemented in `frontend/app/(app)/plugins/page.tsx`.
- `/opencli` exposes a website adapter/capability directory, refresh action, and search by site/domain/capability (`frontend/app/(app)/opencli/page.tsx`).
- `/studio/new` generates a draft from requirements and explicitly computes readiness, capability gaps, and publish/run blocking (`frontend/app/(app)/studio/new/page.tsx`).
- `/studio/projects/[projectId]` renders project readiness cards and the draft → validation → publish steps (`frontend/app/(app)/studio/projects/[projectId]/page.tsx`); project data links to workflow and evidence (`.../data/page.tsx`).
- `/skills` and `/skills/[id]` render skill inventory, evidence history, correction proposal state, dismiss correction, and rollback controls (`frontend/app/(app)/skills/page.tsx`, `frontend/app/(app)/skills/[id]/page.tsx`).
- `/studio/projects/[projectId]/operations`, `/evidence`, and `/data` provide operations, evidence, records, and lineage views; `records/page.tsx` includes a LineagePanel and data page links to workflow/evidence.
- `/operations-agents` is the current schedules/operations surface (the `/schedules` page redirects there). It supports workspace selection, automation/agent views, contract draft editing, conflict handling, publishing, and run/activity views (`frontend/app/(app)/operations-agents/page.tsx`).
- Existing browser coverage: one login rendering test (`frontend/e2e/login.spec.mjs`).
- Existing non-browser coverage: many Node regression scripts, including workflow structure, capability catalog, records/relationships/hygiene, control-plane/dashboard/inbox/navigation checks, and OpenCLI business workflow source contracts. These are valuable guardrails but do not verify user-visible navigation, loading/error states, or interactions.

## Auto-discovered regression candidates (priority order)

### P0-1 Capability catalog and readiness surface — E2E + component/unit
- **Source anchors:** `frontend/app/(app)/plugins/page.tsx:159-200` (`PluginPageTabs`); provider state logic around `providerStateLabel/providerStateTone`; capability detail sheet around `ProviderCard` and capability metrics.
- **Existing anchors:** `frontend/scripts/check-node-capability-catalog-regressions.mjs`, `check-tool-capability-catalog-regressions.mjs`.
- **Plausible bug:** tab selection or readiness state mapping silently regresses, showing a runnable capability as unavailable or making the detail sheet inaccessible.
- **Acceptance:** Navigate to `/plugins`, switch Installed → Node Capabilities → Marketplace using semantic labels; selected tab exposes `aria-current="page"`; a provider card opens its detail sheet and displays declared capabilities plus readiness/missing information. Mock or fixture API responses should cover ready, partial, configuration, and unavailable states.

### P0-2 Studio capability-to-workflow entry and readiness blocking — E2E
- **Source anchors:** `frontend/app/(app)/studio/page.tsx:262-265` (blank/template/import choices); `frontend/app/(app)/studio/new/page.tsx:200-220,328-350,384-387,456-625` (generation, gaps, readiness, save/navigation).
- **Existing anchors:** `frontend/scripts/check-workflow-regressions.mjs`, `check-opencli-business-workflows.mjs`, `test:workflow-contracts`.
- **Plausible bug:** a capability gap is displayed but Publish/Run remains enabled, or the Studio entry loses the project/workflow query parameters after save.
- **Acceptance:** Start from Studio, choose an existing supported template/blank path, submit valid requirements, verify readiness items and generated draft. With a known missing capability, assert Draft can save but publish/run controls are disabled and the gap is visible; with complete requirements, assert navigation reaches the workflow editor with workspace/project/workflow parameters.

### P0-3 Skill correction proposal, dismiss, and rollback — E2E + unit
- **Source anchors:** `frontend/app/(app)/skills/[id]/page.tsx:64-96,159-197` (`openProposal`, `findRollbackTarget`, mutation handlers); evidence rendering `:99-138`.
- **Existing anchors:** no browser test; backend correction tests exist under `tests/skills`/unit coverage.
- **Plausible bug:** an old correction proposal is shown after a later corrected/dismissed boundary, or rollback is offered twice after a rollback event.
- **Acceptance:** Fixture a skill with a current correction proposal; detail shows proposal and dismiss confirmation, dismiss calls the mutation and removes/updates the proposal. Fixture a corrected version; rollback confirmation is available once, success updates history and disables the stale action. Unit-test boundary helpers with corrected/dismissed and already-rolled-back sequences.

### P1-4 Run, evidence, and lineage navigation — E2E
- **Source anchors:** `frontend/app/(app)/studio/projects/[projectId]/operations/page.tsx`, `.../evidence/page.tsx`, `.../data/page.tsx:261-262`; `frontend/app/(app)/records/page.tsx:96-115,330-334`.
- **Existing anchors:** `frontend/scripts/check-record-hygiene-regressions.mjs`, `check-record-relationship-regressions.mjs`; backend `tests/integration/test_workflow_opencli_hda_trace_api.py`.
- **Plausible bug:** selecting a record loses workflow/run/source identifiers or links to evidence with malformed query parameters.
- **Acceptance:** From a project run/record, select a record, verify visible lineage fields (workflow, run, source), open “定位业务编排” and “查看逻辑与证据”, and assert destination URL retains project/workflow/record context. Verify empty and loading states do not render broken links.

### P1-5 Operations Agents contract editing and publish — E2E
- **Source anchors:** `frontend/app/(app)/operations-agents/page.tsx:138-203,209-258,268-283`.
- **Existing anchors:** backend API tests `tests/api/test_operations_agents.py`; no browser coverage.
- **Plausible bug:** provider/model validation is bypassed, JSON contract fields are not persisted, or publish remains enabled without a reason.
- **Acceptance:** Select a workspace and agent, edit role/required capabilities/evidence requirements, verify invalid JSON and provider/model mismatch produce visible errors without mutation; enter valid values, save draft, enter publish reason, publish, and verify success plus version history. A 409 refresh path should show the conflict message and latest revision.

### P1-6 Schedules/automations entry and run/activity view — E2E
- **Source anchors:** `frontend/app/(app)/schedules/page.tsx:1-5` redirect; `frontend/app/(app)/operations-agents/page.tsx:268-283` and automation/run sections later in same file.
- **Existing anchors:** `frontend/scripts/check-dashboard-regressions.mjs`, `tests/api/test_automations.py`, `tests/api/test_automation_starters.py`.
- **Plausible bug:** legacy `/schedules` navigation dead-ends, or starting a run reports success while activity does not refresh.
- **Acceptance:** `/schedules` redirects to `/operations-agents`; automation view loads for a workspace, run action is disabled while pending, success appears in activity, and API error is rendered without duplicate submissions.

### P1-7 OpenCLI website/capability directory search and refresh — E2E + component
- **Source anchors:** `frontend/app/(app)/opencli/page.tsx:150-190,227-230`.
- **Existing anchors:** `frontend/scripts/check-opencli-business-workflows.mjs`, catalog scripts; no browser coverage.
- **Plausible bug:** search filters only labels but not domains/capabilities, or refresh/loading/error states leave stale results.
- **Acceptance:** Directory renders loading then results, search by site/domain/capability narrows cards, refresh shows pending state and replaces results, and API failure shows “网站适配目录暂时不可用” with the error text.

### P2-8 Project readiness and workflow/evidence deep links — E2E
- **Source anchors:** `frontend/app/(app)/studio/projects/[projectId]/page.tsx:202-212,308-310,341-349`; `.../data/page.tsx:261-262`.
- **Existing anchors:** `tests/integration/test_studio_lifecycle_api.py`, `test_workflow_capabilities_api.py`; no browser coverage.
- **Plausible bug:** readiness cards report published status from stale data, or project navigation points at the wrong workflow/evidence route.
- **Acceptance:** Fixture project with/without primary workflow and published version; assert card values and step completion reflect state. Deep links open the correct route and preserve workspace/project identifiers.

## Recommended first batch

Implement P0-1, P0-2, and P0-3 first. They exercise the highest-risk frontend regression seams—capability readiness, the primary Studio creation path, and stateful correction/rollback—and complement existing source-contract checks with actual user-visible behavior. Add shared Playwright API fixtures/mocking only if the current app test harness already supports it; otherwise use deterministic seeded backend data and semantic locators. Keep the tests linear, isolated, and focused on visible outcomes.

## Suggested acceptance gate for the eventual implementation

- New browser specs live under `frontend/e2e` and use `@playwright/test` semantic locators.
- Existing login and Node regression scripts remain unchanged.
- Each candidate has a happy path plus one meaningful error/boundary assertion.
- Run targeted Playwright specs locally, then the repository’s existing `pnpm test:smoke`; this preparation phase intentionally does not run either command.
