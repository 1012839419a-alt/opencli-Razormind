## ADDED Requirements

### Requirement: No wrapper may point at a non-existent endpoint
Every exported wrapper in `frontend/lib/api/endpoints.ts` SHALL correspond to a
backend route that exists in the current tree.

#### Scenario: Wrapper points at a missing route
- **WHEN** `distillSkill` or `restartApi` is examined
- **THEN** either the backend route is implemented (`POST /api/v1/skills/{id}/distill`,
  `POST /api/v1/system/restart`) or the wrapper is removed with a documented
  reason in the change notes.

#### Scenario: Wrapper becomes unused after wiring
- **WHEN** this change wires the CRUD surfaces and the wrapper audit is re-run
- **THEN** the unused-wrapper count is 0, or each remaining unused wrapper has an
  explicit "future work" note in `tasks.md` with an owning task.

### Requirement: Wrapper audit is repeatable
The team SHALL be able to re-run the unused-wrapper audit after this change.

#### Scenario: Re-run the audit
- **WHEN** an operator or CI runs the audit script
- **THEN** it reports per-wrapper reference counts and the unused list.

#### Scenario: Audit is green
- **WHEN** all wrappers are either used or documented
- **THEN** the audit exits 0.
