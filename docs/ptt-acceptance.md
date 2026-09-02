# PTT Acceptance Gate

PTT here means the production trial test gate for the real fleet path. A pass
means the system can be deployed on a NAS or edge host, register an Agent, expose
its runtime capabilities to Fleet, dispatch a workflow to the matched node, and
leave a durable run trace.

Product compass: `openspec/changes/internet-situation-awareness-loop`.
Deployment compass: `openspec/changes/durable-deployment-compass`.

## Scope

PTT-0 is local/static validation. PTT-1 through PTT-5 require a running center
and at least one real Agent node. NetBird is the preferred cross-network path;
LAN is allowed only for a local dry run.

| Gate | Purpose | Pass condition |
|---|---|---|
| PTT-0 Repo sanity | Code, compose, and packaging preflight | Target tests pass, compose config parses, Agent image includes runtime modules |
| PTT-1 Center deploy | Bring up the center on Docker or NAS compose | API responds, `/docs` opens, `docker compose ps` is healthy |
| PTT-2 Agent enroll | Start one remote Agent through install script or Docker run | `/api/v1/nodes` shows the node online with `protocol=ws` or `http` |
| PTT-3 Fleet inventory | Project browser/node/runtime inventory | `/api/v1/workflows/fleet/inventory` shows `runtime.miniflow` for the Agent |
| PTT-4 Runtime dispatch | Send one real `agent_task` to the matched Agent | Agent emits `agent_event` frames and a terminal `agent_result` |
| PTT-5 Workflow trace | Run the Market Situation Monitor workflow through Fleet match | `workflow_run_events` contains match, dispatch, runtime events, result, and failure reason if any |
| PTT-6 OpenTabs smoke | Validate OpenTabs compatibility on a prepared node | `/tools` manifest is projected and a read-only tool call succeeds |

## PTT-0 Local Commands

Run these from the repository root. `uv sync --extra dev` creates and maintains
the repository-local `.venv`; do not call its interpreter directly.

```powershell
uv run pytest `
  tests/unit/test_agent_image_runtime_packaging.py `
  tests/unit/test_agent_server.py `
  tests/unit/test_ws_agent_manager.py `
  tests/unit/agent_runtimes/test_miniflow_adapter.py `
  tests/unit/agent_runtimes/test_opentabs_adapter.py `
  tests/integration/test_workflow_fleet_api.py `
  tests/integration/test_workflow_opencli_hda_trace_api.py `
  --no-cov
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.build.yml config --quiet
```

```powershell
C:\c\Users\Administrator\projects\code-intel-pipeline\Invoke-SentruxAgentTool.ps1 check_rules C:\c\Users\Administrator\projects\opencli-admin-backend
```

## PTT-1 Center Docker Bring-up

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d api agent-1
curl -fsS http://127.0.0.1:8031/docs >/dev/null
```

Evidence:

- `docker compose ps`
- API health or `/docs` reachable
- build log proves `agent/Dockerfile` copied `backend/agent_runtimes` and `backend/miniflow`

## PTT-2 Agent Enroll

For a NetBird node, set the setup key only in the operator shell, not in the
repository:

```bash
export API_AUTH_TOKEN=<center-token>
export NETBIRD_SETUP_KEY=<netbird-setup-key>
curl -fsSL -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://<center-netbird-ip-or-dns>:8031/api/v1/nodes/install/agent.sh | \
  FLEET_NETWORK_PROVIDER=netbird AGENT_REGISTER=ws AGENT_MODE=bridge bash -s -- docker
```

For WireGuard, SSH tunnel, or a custom network, the provider only declares the
reachability path. Bring that path up outside the installer, then pass the
center-reachable agent URL explicitly:

```bash
export API_AUTH_TOKEN=<center-token>
export AGENT_ADVERTISE_URL=http://<agent-wireguard-ip-or-forwarded-host>:19823
curl -fsSL -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://<center-reachable-host>:8031/api/v1/nodes/install/agent.sh | \
  FLEET_NETWORK_PROVIDER=wireguard AGENT_REGISTER=ws AGENT_MODE=bridge bash -s -- docker
```

Pass condition:

```bash
curl -fsS -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://<center>/api/v1/nodes
```

The enrolled node must be online and include a stable label, deploy type, mode,
protocol, last-seen timestamp, and runtime list.

## PTT-3 Fleet Inventory

```bash
curl -fsS -H "Authorization: Bearer $API_AUTH_TOKEN" \
  http://<center>/api/v1/workflows/fleet/inventory
```

Pass condition:

- The Agent appears in `agents[]`.
- `connected=true` for WS enrollment.
- `capabilities[]` includes `runtime.miniflow`.
- OpenTabs nodes include `runtime.opentabs` only when `OPENTABS_BASE_URL` is set
  or the `opentabs` binary is available on that node.

## PTT-4 Runtime Dispatch

Dispatch a MiniFlow workflow file that already exists on the Agent node. For
NAS, use a whitelisted path such as `/volume1/opencli/workflows/market_situation.py`.

Pass condition:

- Center sends an `agent_task` with `runtime=miniflow`.
- Agent emits `started`, per-step `tool_call` and `tool_result`, `state`, then
  terminal `done` or structured `error`.
- Terminal failure still counts as transport pass if it records a typed error
  and audit artifact.

## PTT-5 Workflow Run Trace

Run Market Situation Monitor through the workflow API/UI with Fleet match
enabled.

Pass condition in persisted trace:

- Fleet match event includes selected node endpoint and runtime requirement.
- Dispatch event references the selected Agent.
- Runtime events are written to `workflow_run_events`.
- Result event links any audit artifact path.
- UI can display every step, terminal state, and failure reason.

## PTT-6 OpenTabs Smoke

On the Agent node:

```bash
export OPENTABS_BASE_URL=http://127.0.0.1:9515
export OPENTABS_SECRET=<secret-if-enabled>
```

Pass condition:

- OpenTabs `/health` returns ok.
- `tool.list` returns a non-empty `/tools` manifest.
- One read-only tool call succeeds through `runtime=opentabs`.

## Current Hard Stops

- Docker Agent packaging is part of PTT-0 and must include `backend/agent_runtimes`
  plus `backend/miniflow`; otherwise runtime registration inside the container is
  a false pass.
- Shell/systemd Python install now downloads and validates the authenticated
  `agent-runtime.tar.gz` bundle before installing runtime adapters. Native runtime
  PTT is unblocked at the packaging layer; a real host enrollment is still
  required for PTT-2 through PTT-6.
- MiniFlow workflow file distribution is not solved by Fleet itself. PTT uses a
  pre-positioned NAS path until Git sync, file upload, or a managed workflow
  bundle API is implemented.
- NAS Agent runtime execution is local code execution. PTT must record the
  configured allowlist, workflow directory, bearer token, and audit artifact
  path before the run is accepted.

## 2026-08-24 Local Docker PTT Evidence

This run used isolated local ports `18031` (API), `16080` (noVNC), and
`19824` (remote Agent) because the default ports were already occupied.

| Gate | Result | Evidence |
|---|---|---|
| D0 / PTT-0 | Partial pass | Compose config parsed with isolated credentials; 135 targeted tests passed; `code-intel sentrux check .` rules passed. OpenSpec CLI is unavailable and the Sentrux baseline is missing. |
| D1 / PTT-1 | Pass | API image and Agent image built; API `/health` returned `{"status":"ok"}`; `/docs` and the built-in browser Agent were healthy. |
| D2 / PTT-2 persistence | Pass | API and built-in browser Agent restarted; health stayed green, the workspace, published Operations Agent, completed MiniFlow run, and online WS node were readable afterward. |
| D3 / PTT-2/3 enrollment | Pass | WS Agent `http://host.docker.internal:19824` registered online with `runtimes=["miniflow"]`; Fleet inventory projected `runtime.miniflow`. |
| D4 / PTT-4 runtime dispatch | Pass | Operations Agent run `9688b25a-26e7-46be-99de-4e6496390202` completed through the real WS path; MiniFlow `ptt-smoke` ran one successful `probe` step and wrote `/tmp/ptt/audit.jsonl`. |
| D5 / PTT-5 workflow trace | Blocked | The real three-feed Market Situation workflow produced 27 trace events, but all external RSS fetches were blocked because the environment DNS resolved public hosts to `198.18.0.x`, which the SSRF guard correctly rejects; zero records were stored. |
| D6 backup/restore | Pass | `snailfish_db_data` and Agent profile were archived to `snailfish_ptt_backup`; DB state restored to `snailfish_ptt_restore` and queried successfully (`1` workspace, `1` completed runtime run). |
| D7 upgrade/rollback | Pass | Rebuilt API image, then launched the locally retained pre-change API image `10f2c4b565a7` against `snailfish_ptt_restore`; `/health` passed and the restored workspace was readable through the old image. |
PTT-6 OpenTabs smoke remains unproven: this evidence run did not verify the
OpenTabs `/health`, `/tools` manifest, or a read-only `runtime=opentabs` call.
Production NAS/edge/NetBird acceptance also remains unproven; this evidence is
for isolated local Docker only.

The D5 result remains a hard blocker for promoting this deployment profile to
`supported`; it is not converted into passing evidence.
## Live Adapter Kernel Smoke

On 2026-08-24, the real RSS adapter/kernel path was exercised against the
backend at `http://127.0.0.1:18041` using an ephemeral RSS fixture at
`http://127.0.0.1:18042`. The run used `POST /api/v1/workflows/runs` with
`runId=live-local-rss-20260824-1110` and returned HTTP `202`,
`valid=true`, `status=completed`, and `eventCount=22`.

- Source batch: `itemCount=1`.
- Normalize batch: `recordCount=1`.
- Trace: `status=completed`, `lastSequence=22`.
- Failed/blocked events: none.

The public RSS trial remains blocked because the environment's DNS sinkhole
resolves public hosts to `198.18.*`, which the SSRF guard correctly rejects.
This local fixture proves the real adapter/kernel execution path only; it does
not prove internet reachability or public RSS acceptance.

## 2026-08-24 Multi-agent Business Acceptance

The authenticated business path was exercised against the actual backend
entrypoint (`backend.main:app`) at `127.0.0.1:18042`, using a process-isolated
temporary SQLite database. `GET /health`, `/docs`, `/api/v1/auth/me`,
`/api/v1/workflows/capabilities`, and `/api/v1/workflows/fleet/inventory` all
returned HTTP `200`. Workspace/project bootstrap succeeded, followed by draft
read/update, validation, and publish.

The final studio run was `36aac778-5a2a-574c-aeec-0d726a0dd73b`, with trace
`e867db35-e256-498d-ad06-8b285a22a69d`: `status=completed`,
`valid=true`, and `eventCount=19`. The real local RSS adapter/kernel fetched
`2` RSS items and produced `2` evidence batches. The project trace was
readable with events, projection, and checkpoint data. Generic replay run
`acceptance-generic-rss` was also completed with `19` events, `2` projection
artifacts, and `2` evidence batches.

The first schedule-only manual run failed correctly with
`workflow_trigger_kind_mismatch`; adding an explicit manual trigger and
republishing fixed the operator path. A direct private RSS URL was correctly
blocked by the SSRF guard; configuring a provider route with local-fixture
private-network allowance enabled the controlled local RSS acceptance. This
does not claim public internet success.

Frontend evidence: typecheck and lint passed; the top-right Agent entry opened
`/operations-agents`, the bottom-right bubble opened the conversation dock,
and the sidebar Automation entry opened `/schedules`. Workflow-editor browser
click-through and backend-connected frontend project data remain unverified.
## 2026-08-25 Full Test Sweep

This run is not a clean full-suite gate; blocked, cancelled, and failing checks
remain explicitly recorded.

- Backend environment: `uv sync --extra dev` passed.
- Backend full suite: `uv run pytest` collected `2755` tests, then was bounded
  and cancelled at
  `tests/integration/test_chat_api.py::test_viewer_confirmation_is_denied_without_mutation`
  after `127` passed, `2` skipped, and `0` failed. The standalone viewer test
  passed, but its overall command exited `1` because coverage was `32.84%`,
  below the configured `80%` threshold.
- Backend lint: `ruff check backend tests` found `568` diagnostics in `265`
  files.
- Frontend: typecheck, lint, and build passed. Deterministic checks reported
  `141` passes and `4` stale-contract failures. Playwright smoke was blocked by
  `EADDRINUSE` on port `3000` and the login-token label.

These results do not constitute a passing full-suite acceptance gate.
