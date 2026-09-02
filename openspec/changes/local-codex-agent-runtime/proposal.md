## Why

The local workstation has a usable Codex CLI, but the Operations Agent UI currently treats `codex` as an automation label rather than an executable runtime. Selecting Codex can persist an Automation record, yet no Fleet runtime capability, local runner, event adapter, or terminal result contract proves that the task actually ran.

The same gap affects the three Agent Starters introduced for the control plane:

- 运行简报 Agent
- 系统回顾 Agent
- 异常跟进 Agent

The product must also be honest about provider capacity. Local Claude Code and Codex CLIs do not provide a stable, portable five-hour quota API that the control plane can infer. The UI must report `unknown` when usage cannot be read rather than inventing remaining capacity or cutting a task short based on elapsed time.

## What Changes

- Add a governed `runtime.codex` local Agent runner and Fleet capability contract.
- Execute Codex on a registered user workstation through the existing Agent transport instead of spawning a user binary from the web/API process.
- Translate Codex process output into the existing Agent event set: started, text, tool_call, tool_result, state, done, and error.
- Add health/readiness evidence for the Codex binary and its working directory before dispatch.
- Make the three Agent Starters idempotent, runnable, and traceable through the existing Automation and Operations Agent APIs.
- Reuse the existing SmoothUI Agent Avatar and Switchboard Card components for starter discovery and runtime status; do not add a parallel visual component system.
- Raise the governed default execution timeout to the deep-run profile while keeping a hard upper bound and explicit approval mode.
- Add a provider-capacity projection with three states: measured, unavailable, and not applicable. Never infer provider quota from wall-clock duration.

## Capabilities

### New Capabilities

- `codex-local-runtime`: Governed Codex CLI execution on a registered local Agent node with streamed events and terminal evidence.
- `agent-starter-installation`: Idempotent installation and traceable execution of the three first-party Agent Starters.
- `provider-capacity-visibility`: Honest provider usage state with optional provider-specific usage adapters and an explicit unknown state.

### Modified Capabilities

- `operations-agent-runtime`: Add `runtime.codex` as an optional runtime binding; preserve existing MiniFlow and Pi contracts.
- `agent-execution-depth`: Use the deep-run timeout profile without treating it as a quota bypass.
- `operations-agent-ui`: Use existing SmoothUI primitives for Agent starter cards and runtime state.

## Impact

- Backend Agent runtime registry, local Agent runner, Fleet capability projection, and event normalization.
- Operations Agent runtime binding validation and dispatch timeout defaults.
- Automation starter installation and duplicate detection.
- Provider usage/capacity projection APIs and UI.
- SmoothUI-backed Operations Agent page and provider page.
- Focused runtime, API, and frontend interaction tests.

## Non-Goals

- Do not claim to read Claude Code, Codex, or any provider's five-hour quota when no supported usage endpoint exists.
- Do not bypass local Agent registration, workspace permissions, approval gates, or project path confinement.
- Do not spawn arbitrary user commands from the API server merely because a browser machine has a CLI installed.
- Do not introduce a second run/event persistence model outside Operations Agent Run and the existing Fleet transport.
