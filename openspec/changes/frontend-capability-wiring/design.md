## Context

The audit (2026-08-08) counted **140 exported API wrappers** in
`frontend/lib/api/endpoints.ts`; **54 are never imported** by any component.
Every resource domain (skills, agents, providers, schedules, records, sources,
plans, nodes, browser bindings, notification rules, system) has complete backend
routes but partial or missing UI. The `/skills` table shows a "待复核" badge with
no click target; `/agents` renders a dead empty state; `/providers` is a
read-only card; `/schedules`, `/records`, `/plans`, `/sources`, `/nodes` are
read-only shells. Two wrappers (`distillSkill`, `restartApi`) point at backend
files that do not expose the expected route — they are latent 404s.

This change is scoped to **wiring what already exists**: every wrapper that maps
to a live backend route gets a UI path; wrappers that cannot work are removed or
backend-fixed.

## Decisions

1. **Wire before build.** Only surfaces backed by an existing endpoint are in
   scope. If a wrapper has no backend route and no product direction calls for
   one, we remove it rather than invent a backend.
   - Rationale: the audit shows the platform's gap is UI reachability, not
     backend capability. Building new endpoints here would expand scope and
     delay the higher-value wiring work.

2. **Skill correction workflow ships first (P0).** It is the smallest complete
   loop: one new detail route (`/skills/[skill_id]`), three action buttons, all
   backed by live routes. It also unblocks the most visible "dead badge" in the
   UI.
   - Rationale: highest value per unit of risk; it exercises the pattern
     (detail page + action buttons + inline errors) that the other surfaces
     will reuse.

3. **Agent create form kills the dead empty state (P0).** The `/agents` page
   currently tells the operator to create an agent but offers no form. Adding
   create/edit/delete turns a trap into a working surface using hooks that
   already exist.
   - Rationale: empty-state copy without an action is the clearest example of a
     "looks done, isn't" page; fixing it is cheap.

4. **Provider CRUD stays beside the read-only card.** We keep `PrimaryModelCard`
   and add management actions around it rather than replacing the card.
   - Rationale: the card is the operator's at-a-glance view; CRUD belongs in a
     dialog/drawer next to it, not in a separate page that splits the context.

5. **`distillSkill` and `restartApi` are resolved by removal unless a backend
   owner confirms otherwise.** Both point at files whose routes do not include
   the expected path. Removing them (with a change note) is safer than leaving
   latent 404s; implementing new backend endpoints is a separate change.
   - Rationale: an unused wrapper is dead code; a wrapper that 404s when finally
     used is a trap. Removing keeps the audit green without expanding scope.

6. **Navigation changes are minimal and mechanical.** `/control` moves to its
   own group (it is a control surface, not a model connection); `/sources` and
   `/canvas` get sidebar entries only if they are real destinations with pages.
   - Rationale: nav churn has regression risk (check-navigation scripts); we
     only change what the audit showed is mislabeled or unreachable.

7. **The wrapper audit becomes a checked-in script.** A small
   `scripts/audit-unused-wrappers.mjs` (or python) that reports per-wrapper
   reference counts, so CI can enforce "no unused wrappers" going forward.
   - Rationale: without a gate, the 54-wrapper debt will regrow as new
     endpoints are added.

## Sequence

1. P0: skill correction workflow (`/skills/[skill_id]` + actions).
2. P0: agents create/edit/delete.
3. P1: providers CRUD, schedules CRUD, records actions.
4. P1: sources management, plans actions, nodes detail/delete.
5. P2: dead-wrapper resolution, navigation tweaks, audit script.
6. Verification: tsc, lint, regression scripts, wrapper audit re-run.

## Risks

- Frontend regression scripts (`check-workflow-regressions.mjs`,
  `check-navigation-transition-regressions.mjs`) may assert nav structure or
  specific pages; nav changes could break them. Mitigation: run them before/after
  and keep nav changes minimal.
- Provider/schedule forms need shared form components; if the project lacks a
  form primitives layer, we reuse `components/ui/dialog` + existing inputs to
  avoid adding a new dependency.
- The two dead wrappers might actually be intended for a future backend;
  removing them is reversible (git history), and the change note documents it.
