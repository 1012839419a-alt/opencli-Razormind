## 1. Contract

- [x] 1.1 Define the `runtime.codex` capability, transport boundary, supported event mapping, and terminal result contract.
- [x] 1.2 Define the deep-run execution profile, timeout ceiling, approval behavior, project-path confinement, and cancellation semantics.
- [x] 1.3 Define provider-capacity states (`measured`, `unavailable`, `not_applicable`) and prohibit inferred quota values.
- [x] 1.4 Define the three Agent Starter templates, stable keys, schedules, executor bindings, and idempotent installation rules.

## 2. Local Codex Runtime

- [x] 2.1 Add a local Agent Codex runner that validates `codex --version`, working directory, branch, and configured binary before dispatch.
- [x] 2.2 Register `runtime.codex` in the Agent capability registry and expose readiness diagnostics without leaking credentials.
- [x] 2.3 Stream Codex output into the existing Agent event envelope and persist state/output/error through Operations Agent Run.
- [x] 2.4 Enforce workspace path confinement, approval mode, timeout, cancellation, and non-zero exit handling.
- [x] 2.5 Add focused adapter tests for healthy, missing-binary, invalid-path, timeout, cancellation, tool-event, and terminal-result cases.

## 3. Agent Starters

- [x] 3.1 Add idempotent create/install behavior for 运行简报 Agent, 系统回顾 Agent, and 异常跟进 Agent.
- [x] 3.2 Bind each starter to its intended executor/runtime and expose the selected binding in the UI.
- [ ] 3.3 Persist starter-created automation/run lineage and show recent status in the Operations Agent activity view.
- [ ] 3.4 Add API tests for first install, repeated install, partial install failure, and starter run dispatch.

## 4. Capacity Visibility

- [ ] 4.1 Add provider usage adapter interfaces without assuming a shared quota schema.
- [ ] 4.2 Implement measured usage only for providers with a documented usage endpoint.
- [x] 4.3 Return explicit unknown state for local Claude Code/Codex when the CLI cannot report quota.
- [ ] 4.4 Add UI states and tests proving unknown capacity never renders as zero, 100%, or a guessed remaining amount.

## 5. UI Integration

- [x] 5.1 Keep SmoothUI Switchboard Card and Agent Avatar as the starter and runtime visual primitives.
- [ ] 5.2 Add deep-run state, runtime readiness, capacity state, and approval state to the existing Agent surfaces.
- [ ] 5.3 Add responsive browser smoke coverage for starter installation, runtime status, and unknown capacity.

## 6. Verification

- [x] 6.1 Run focused backend runtime and Operations Agent tests.
- [ ] 6.2 Run frontend lint, typecheck, build, and targeted interaction checks.
- [x] 6.3 Run `openspec validate local-codex-agent-runtime --strict`.
- [x] 6.4 Run Code Intel/Sentrux session gates and record provider-capacity limitations as explicit evidence.
