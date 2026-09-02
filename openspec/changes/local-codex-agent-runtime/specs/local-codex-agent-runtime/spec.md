# Local Codex Agent Runtime

## ADDED Requirements

### Requirement: Codex runtime readiness is explicit

The system MUST expose a readiness result for a registered local Agent before dispatching a Codex run.

The readiness result MUST include:

- whether the `codex` binary is present;
- the detected Codex version when available;
- the permitted project root and working directory;
- the runtime capability identifier `runtime.codex`;
- a typed failure reason when the binary, path, or Agent connection is unavailable.

The readiness result MUST NOT include API keys, session tokens, or raw provider credentials.

#### Scenario: Local Codex is installed

- **WHEN** a registered Agent reports a valid Codex binary and permitted project path
- **THEN** the Fleet capability inventory MUST mark `runtime.codex` as ready
- **AND** the Operations Agent UI MUST allow a run to be submitted

#### Scenario: Local Codex is missing

- **WHEN** the Agent cannot resolve the configured Codex binary
- **THEN** readiness MUST be `blocked`
- **AND** the UI MUST show the missing-binary reason
- **AND** the API MUST NOT enqueue a run that cannot start

### Requirement: Codex execution uses the existing Agent transport

The control plane MUST dispatch Codex through an authenticated registered Agent connection.

The API server MUST NOT invoke a user workstation's Codex binary directly from a browser request or by assuming that a local CLI exists on the API host.

#### Scenario: Codex run dispatch

- **WHEN** a permitted Operations Agent run targets `runtime.codex`
- **THEN** the registered Agent MUST receive the task through the existing transport
- **AND** the control plane MUST persist the run as `running`
- **AND** streamed runtime events MUST be normalized into the existing event envelope

### Requirement: Codex terminal evidence is durable

A Codex run MUST finish with exactly one terminal `done` or `error` event.

The run MUST persist:

- normalized text/tool/state events as available;
- the terminal result or typed error;
- process exit status when available;
- timeout or cancellation reason when applicable;
- the runtime identity and Codex version used for the run.

#### Scenario: Codex exits successfully

- **WHEN** the Codex process exits with a successful terminal response
- **THEN** the Operations Agent Run MUST become `completed`
- **AND** its output MUST be available to the activity view

#### Scenario: Codex exceeds the deep-run timeout

- **WHEN** the Codex process exceeds the configured deep-run timeout
- **THEN** the Agent MUST cancel the process
- **AND** the run MUST become `failed` with a typed timeout reason
- **AND** the system MUST NOT claim that the provider quota was exhausted

### Requirement: Provider capacity is honest

The control plane MUST distinguish between measured usage and unavailable usage.

A provider capacity projection MUST use one of:

- `measured`: a documented provider usage endpoint returned valid data;
- `unavailable`: the provider or local CLI does not expose a supported usage endpoint;
- `not_applicable`: the runtime does not have provider quota semantics.

#### Scenario: Local Claude Code or Codex has no quota API

- **WHEN** the local CLI cannot report its five-hour usage window
- **THEN** the UI MUST show `unavailable`
- **AND** it MUST NOT render a guessed remaining percentage
- **AND** task execution MUST continue according to runtime completion, approval, and timeout policy

### Requirement: Starter installation is idempotent

The platform MUST provide stable first-party starter keys for:

- `daily-run-brief`
- `weekly-system-review`
- `anomaly-follow-up`

Installing starters MUST skip an existing starter with the same workspace and stable key.

#### Scenario: First installation

- **WHEN** an administrator installs the starter pack in a Workspace
- **THEN** all missing starters MUST be created through the existing Automation API
- **AND** each starter MUST retain its executor, schedule, approval mode, and lineage

#### Scenario: Repeated installation

- **WHEN** the same starter pack is installed again
- **THEN** existing starters MUST NOT be duplicated
- **AND** the response MUST report created and skipped counts
