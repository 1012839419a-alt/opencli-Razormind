## Why

The backend exposes 140 API client wrappers (`frontend/lib/api/endpoints.ts`) and
46 route files covering every resource domain. But an audit of the running UI
shows **54 of those wrappers are never imported anywhere** in `frontend/`, and
several navigation destinations render read-only shells or dead empty states:

- `/skills` shows a "待复核" (pending review) badge with **no click target** —
  the correction detail view, dismiss, and rollback actions are all wired in
  the backend (`GET /{skill_id}`, `POST /{skill_id}/dismiss-correction`,
  `POST /{skill_id}/rollback`, `POST /{skill_id}/redistill`) but missing from UI.
- `/agents` renders "暂无智能体 / 创建 AI 智能体以处理采集到的数据" with **no
  create form** — `createAgent`/`updateAgent`/`deleteAgent` exist unused.
- `/providers` is a read-only `PrimaryModelCard`; provider CRUD hooks exist but
  are never mounted.
- `/schedules`, `/records`, `/plans`, `/plugins`, `/sources`, `/nodes` are
  read-only lists or shells; their CRUD wrappers are unused.
- `distillSkill` points at `skill_bridge.py` which only exposes `/invoke`, and
  `restartApi` points at `system.py` which only exposes `/config` — two wrappers
  that would 404 if ever mounted. These need a backend decision, not just UI.

This change closes the gap: every backend capability that is already shipped
must have a working, reachable UI path, and wrappers that cannot work must be
fixed or removed rather than left as traps.

## What Changes

- Add a skill correction detail view reachable from the `/skills` table's
  "待复核" badge, with dismiss / rollback / redistill actions backed by the
  existing endpoints.
- Replace the `/agents` dead empty state with a real create-agent form; add
  edit/delete actions backed by `createAgent`/`updateAgent`/`deleteAgent`.
- Add provider create/edit/delete/test UI under `/providers` backed by the
  existing provider hooks.
- Add CRUD actions to `/schedules`, `/records` (detail + delete + batch-delete +
  clear-all), `/sources` (create/delete + credential management), `/plans`
  (create/edit/delete/run), and `/nodes` (detail + delete) using the wrappers
  that already exist and are currently unused.
- Resolve the two dead wrappers: either implement the backend endpoints
  (`POST /system/restart`, skill `distill` under the skills router) or remove
  the wrappers with a documented reason.
- Wire the system-management wrappers (`getSystemConfig`, `updateSystemConfig`,
  `getCeleryStats`, `getWsAgentStatus`) into a settings surface reachable from
  navigation, or explicitly mark them as future work.

## Capabilities

### New Capabilities

- `skill-correction-workflow`: correction detail view with dismiss, rollback,
  and redistill actions for skills with open proposals.
- `resource-crud-surfaces`: create/edit/delete/test surfaces for agents,
  providers, schedules, records, sources, plans, and nodes that currently have
  backend endpoints but no UI.
- `dead-wrapper-cleanup`: remove or backend-fix wrappers that point at
  non-existent endpoints (`distillSkill`, `restartApi`) and delete wrappers that
  remain unused after this change with an explicit non-goal note.

### Modified Capabilities

- `navigation`: `/control` should move out of the "模型与连接" group into its
  own "运行与数据" or "管理" subgroup, and `/sources` + `/canvas` should get
  sidebar entries (they are currently URL-only).

## Impact

- `frontend/app/(app)/skills/page.tsx` + new correction detail component.
- `frontend/app/(app)/agents/page.tsx` + create/edit forms.
- `frontend/app/(app)/providers/page.tsx` + provider management UI.
- `frontend/app/(app)/schedules/page.tsx`, `records/page.tsx`, `sources/page.tsx`,
  `plans/page.tsx`, `nodes/page.tsx` — add CRUD actions.
- `frontend/lib/navigation.ts` — nav group restructure.
- `frontend/lib/api/endpoints.ts` — remove dead wrappers or add backend fixes.
- Optional backend: `backend/api/v1/system.py` (`POST /restart`), skills distill
  endpoint, if we choose to implement rather than remove.
- Frontend regression scripts (`scripts/check-*.mjs`) may need updates for new
  nav/routes.

## Non-Goals

- Do not rebuild the whole studio/canvas editor in this change.
- Do not add a full settings/administration console — only wire what has
  backend endpoints today.
- Do not implement `distillSkill`/`restartApi` backends unless they are already
  part of an accepted product direction; otherwise remove the wrappers.
- Do not touch `global-agent-dock.tsx` or the agent-execution-experience
  surface (separate change).
