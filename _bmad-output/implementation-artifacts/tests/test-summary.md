# Test Automation Summary

## Generated Tests

### API Tests
- [x] Not applicable: this QA batch targets existing frontend user workflows; API behavior is exercised through deterministic Playwright route fixtures and existing repository contract tests.

### E2E Tests
- [x] `frontend/e2e/p0-regressions.spec.mjs` — P0-1 Plugin Center installed → node capabilities → marketplace tabs, `aria-current` selection, and generic provider capability detail/readiness surface.
- [x] `frontend/e2e/p0-regressions.spec.mjs` — P0-3 Skill detail current correction proposal, dismiss confirmation, corrected-version rollback, and stale rollback prevention after `rolled_back`.
- [x] P0-2 Studio readiness/gap behavior is covered by existing deterministic Node workflow regressions, not a newly passing browser test. The attempted Studio E2E was removed because React hydration/remount made the interaction flaky under the current production Next harness. This summary does not claim Studio E2E coverage.

## Coverage

| Discovered target | Priority | Coverage status | Evidence / notes |
|---|---:|---|---|
| Plugin capability catalog, readiness states, and tabs/detail | P0-1 | Covered — E2E | `frontend/e2e/p0-regressions.spec.mjs`; deterministic plugin/capability fixtures; semantic tab and detail assertions |
| Studio capability-to-workflow entry and readiness blocking | P0-2 | Covered — deterministic Node contract; no E2E | Existing `check-workflow-regressions` Agent Builder readiness/gap tests prove `canSave=true`, `canPublish=false`, `canRun=false`, blocking actions, and complete-path readiness; browser attempt removed as flaky hydration/remount |
| Skill correction proposal, dismiss, and rollback | P0-3 | Covered — E2E | `frontend/e2e/p0-regressions.spec.mjs`; deterministic skill evidence and POST mutation fixtures |
| Run, evidence, and lineage navigation | P1-4 | Remaining candidate | Planned; no new test generated in this batch |
| Operations Agents contract editing and publish | P1-5 | Remaining candidate | Planned; no new test generated in this batch |
| Schedules/automations entry and run/activity | P1-6 | Remaining candidate | Planned; no new test generated in this batch |
| OpenCLI website/capability directory search and refresh | P1-7 | Remaining candidate | Planned; no new test generated in this batch |
| Project readiness and workflow/evidence deep links | P2-8 | Remaining candidate | Planned; no new test generated in this batch |

## Verification Evidence

- Targeted P0 Playwright with `--repeat-each=3`: **6/6 passed** (P0-1 and P0-3, each repeated three times).
- Normal P0 Playwright run: **2/2 passed**.
- Existing frontend smoke (`pnpm test:smoke`): **3/3 passed**.
- Workflow regression contracts (`pnpm run check:workflow-regressions`, including inspector workflow checks): **60/60 passed**.
- Node capability/catalog contracts (`pnpm run check:node-capabilities`, which includes the capability/tool catalog checks): **16/16 passed**.
- Targeted E2E lint (`pnpm exec eslint e2e/p0-regressions.spec.mjs`): **passed**.

## Infrastructure Notes

- Existing warning: Playwright's configured `next start --hostname 127.0.0.1 --port 3000` reports that `next start` is incompatible with the app's `output: standalone` configuration.
- `pnpm build` succeeded. A source-grounded attempt to run `.next/standalone/server.js` on Windows failed before serving with `EPERM` while stat'ing the bundled pnpm React path. This is a test-infrastructure follow-up, not a product regression.
- The alias command `check:tool-capability-catalog-regressions` is absent from `frontend/package.json`; the repository's existing `check:node-capabilities` script includes the tool capability catalog test and passed (16/16).

## Checklist Outcome

Validated against `skill://bmad-qa-generate-e2e-tests/checklist.md`:

- API tests: **N/A** for this frontend workflow batch.
- E2E tests: **PASS** for the generated P0-1/P0-3 browser tests.
- Standard framework APIs and semantic locators: **PASS** (Playwright and Node `node:test`; accessible roles/labels/text).
- Happy paths and critical boundary/error behavior: **PASS** for generated P0 tests and existing P0-2 Node contract coverage.
- All generated tests run successfully: **PASS** (6/6 repeated and 2/2 normal).
- Test independence and clear descriptions: **PASS**; each Playwright test uses its own context and deterministic route fixtures.
- No hardcoded waits/sleeps: **PASS** in the final generated tests; bounded Playwright expectations are used for asynchronous UI state.
- Summary, test locations, and coverage metrics: **PASS**; this file and the prior discovery plan are saved under implementation artifacts.
- Validation commands: **PASS** for the executed targeted P0, smoke, workflow, and capability contract commands listed above.

Overall checklist result: **PASS with documented infrastructure follow-up and explicit Studio E2E gap**.

## Scope and Changes

- No production source changed.
- Test-only change: `frontend/e2e/p0-regressions.spec.mjs`.
- Documentation artifact: `_bmad-output/implementation-artifacts/tests/frontend-regression-plan.md` and this summary.

## Next Steps

- Keep the deterministic Node Studio readiness contract as the regression gate.
- Revisit Studio browser interaction after the Next/React hydration/remount harness is made stable; do not treat the removed attempt as E2E coverage.
- Prioritize the remaining P1/P2 candidates from the regression plan.
