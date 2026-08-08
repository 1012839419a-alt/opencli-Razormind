# Frontend Capability Wiring

Close the gap between the 140 backend API wrappers and the UI: wire the 54
currently-unused wrappers into working surfaces, fix the dead empty states
(`/agents`), add the skill correction workflow (`/skills/[skill_id]` +
dismiss/rollback/redistill), add CRUD to providers/schedules/records/sources/
plans/nodes, resolve the two dead wrappers (`distillSkill`, `restartApi`), and
make the wrapper audit repeatable.

## Artifacts

- `proposal.md` — why / what / capabilities / non-goals
- `design.md` — decisions and rationale
- `specs/skill-correction-workflow/spec.md` — correction detail + actions
- `specs/resource-crud-surfaces/spec.md` — agents/providers/schedules/records/
  sources/plans/nodes CRUD
- `specs/dead-wrapper-cleanup/spec.md` — no wrapper points at a missing route;
  audit is repeatable
- `tasks.md` — implementation checklist

## Status

Draft — created 2026-08-08, pending review before implementation.
