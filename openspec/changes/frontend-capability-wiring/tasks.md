## 1. Skill Correction Workflow

- [ ] 1.1 Add `useSkill(id)` hook wrapping `getSkill` (or reuse `useSkills` + filter).
- [ ] 1.2 Create `frontend/app/(app)/skills/[skill_id]/page.tsx` detail view showing name, domain, capability, version, evidence count, proposal body.
- [ ] 1.3 Link the "待复核" badge in the `/skills` table to `/skills/{skill_id}`.
- [ ] 1.4 Add dismiss button → `dismissCorrection(skill_id)` with inline error handling + success toast + refresh.
- [ ] 1.5 Add rollback button → `rollbackSkill(skill_id)` with confirmation dialog.
- [ ] 1.6 Add redistill button → `redistillSkill(skill_id)` with pending state.
- [ ] 1.7 Verify the correction workflow against the backend routes in `backend/api/v1/skills.py`.

## 2. Resource CRUD Surfaces

- [ ] 2.1 `/agents`: replace EmptyState with create form (name/description/profile) calling `createAgent`; add edit/delete per row.
- [ ] 2.2 `/providers`: add create/edit/delete/test UI beside `PrimaryModelCard` using existing provider hooks.
- [ ] 2.3 `/schedules`: add create/update/delete form + row actions.
- [ ] 2.4 `/records`: add detail view, single delete, batch delete (selection), clear-all (confirm dialog).
- [ ] 2.5 `/sources`: add create/delete, connectivity test, credential management drawer.
- [ ] 2.6 `/plans`: add create/edit/delete/run + `getPlanHealth` indicator.
- [ ] 2.7 `/nodes`: add detail (events/stats) + delete.
- [ ] 2.8 Add shared form/modal components if not already present (`components/ui/dialog`, `components/ui/form`).

## 3. Dead Wrapper Cleanup

- [ ] 3.1 Decide backend vs removal for `distillSkill` (skills router) and `restartApi` (system router); implement or remove.
- [ ] 3.2 Re-run the unused-wrapper audit; confirm count is 0 or remaining items are documented in tasks with owners.
- [ ] 3.3 Add the audit as a script (`scripts/audit-unused-wrappers.mjs`) so CI can enforce it.

## 4. Navigation

- [ ] 4.1 Move `/control` (+ `/control/actions`) out of the "模型与连接" group into an appropriate group ("运行与数据" or its own "管理" subgroup).
- [ ] 4.2 Add sidebar entries for `/sources` (数据) and `/canvas` (节点工作流) if they are real destinations.
- [ ] 4.3 Update `ROUTE_LABELS` for any moved/added routes.
- [ ] 4.4 Check `scripts/check-navigation-transition-regressions.mjs` still passes after nav changes.

## 5. Verification

- [ ] 5.1 `pnpm exec tsc --noEmit` passes.
- [ ] 5.2 `pnpm lint` passes.
- [ ] 5.3 `pnpm check:*` regression scripts pass (or failures match main baseline).
- [ ] 5.4 Backend: `uv run python -m pytest tests/unit tests/integration -q --no-cov` passes if backend touched.
- [ ] 5.5 Re-run wrapper audit → 0 unused (or all documented).
- [ ] 5.6 `openspec validate frontend-capability-wiring --strict` (if CLI available) or manual review of artifacts.
