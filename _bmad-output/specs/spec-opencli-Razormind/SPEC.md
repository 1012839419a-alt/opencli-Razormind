---
id: SPEC-opencli-Razormind
companions:
  - brownfield.md
  - portability.md
  - source-chain.md
sources:
  - ../../planning-artifacts/briefs/brief-opencli-Razormind-2026-08-24/brief.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only.

# OpenCLI Local Deep Research Data Upstream

## Why

Researchers and downstream Agents need current information, but heterogeneous sources, fragile acquisition, fragmented provenance, and chat-only automation make research difficult to reproduce or reuse. OpenCLI already contains substantial acquisition, workflow, evidence, Agent-control, and self-hosting foundations. The work is to converge them into a local-first Deep Research upstream whose intelligence is grounded in a durable source chain rather than rebuild another crawler UI or SaaS operations platform.

## Capabilities

- **CAP-1 — Persistent Research Projects**
  - **intent:** An Agent or human can turn a research objective into one durable project containing its workflow, sources, runs, evidence, and revisions.
  - **success:** After restart or session change, the project can resume from its persisted state and every run resolves to the project and exact workflow revision that produced it.

- **CAP-2 — Real-time Multi-source Acquisition**
  - **intent:** A project can continuously acquire current information through governed browser, web, API, RSS, and OpenCLI/plugin sources.
  - **success:** A live mixed-source run records an outcome for every configured source, preserves successful results during partial failure, and reports blocked or failed sources without claiming completeness.

- **CAP-3 — Verifiable Source Chain**
  - **intent:** A consumer can trace every research claim and citation back through transformations to preserved source material and acquisition context.
  - **success:** Given any published research claim, an API query resolves its citation, transformed record, raw snapshot or artifact, source identity, acquisition timestamp, run, and workflow version; any missing link makes the claim non-authoritative.

- **CAP-4 — Deep Research Orchestration**
  - **intent:** The system can decompose a research objective, coordinate multi-source retrieval, identify conflicts and evidence gaps, and produce a structured evidence-backed research output.
  - **success:** A reference research task produces a persisted plan, source-backed findings, explicit conflicts and unresolved gaps, and citations that pass CAP-3 trace verification.

- **CAP-5 — Agent and System Consumption**
  - **intent:** Downstream Agents and systems can discover capabilities and consume normalized records, evidence, provenance, run state, and research outputs through stable machine contracts.
  - **success:** An external Agent completes the reference research journey through MCP or HTTP without scraping the UI, and receives versioned schemas plus stable identifiers shared with the first-party interface.

- **CAP-6 — Governed Reusable Extensions**
  - **intent:** Operators can install and reuse versioned source adapters, browser nodes, transforms, research operators, and optional sinks as workflow/plugin capabilities.
  - **success:** A certified extension declares typed inputs and outputs, version, readiness, permissions, and failure semantics; it compiles and runs when ready, while forged, stale, unverified, or unsafe capabilities fail closed.

- **CAP-7 — Local Deployment and Recovery**
  - **intent:** An operator can install, configure, run, observe, upgrade, and recover the complete platform on local infrastructure.
  - **success:** A clean supported host passes an authenticated install-and-run smoke journey, executes the reference research task, retains data across restart, and restores operation without an OpenCLI-hosted SaaS dependency.

- **CAP-8 — Unified Agent and Visual Editing**
  - **intent:** Agent interaction and manual UI operate the same authoritative project and workflow state without chat-only shadow objects.
  - **success:** Agent and human edits carry base revisions and concrete diffs; non-conflicting changes preserve both edits, conflicting or stale changes cannot overwrite newer state, and accepted changes appear identically through UI and API.

- **CAP-9 — Portable Project and Workflow Transfer**
  - **intent:** An operator can move a previously authored project or workflow between OpenCLI instances, devices, and LAN deployments without rebuilding it manually.
  - **success:** Both a Workflow Package and a Full Project Package export from instance A import into a clean instance B with their profile-specific content preserved, produce explicit compatibility and missing-dependency reports, expose connection remapping without exporting secrets, and pass their independent conformance journeys after reported gaps are repaired.

## Constraints

- Source-chain integrity is the highest-priority invariant: synthesis without resolvable citations and preserved source evidence cannot be authoritative.
- Core acquisition, research, storage, and consumption must run locally; hosted coordination may be optional but cannot be required.
- Reuse merged and verified OpenCLI contracts. Catalog entries, previews, fixtures, open Issues, and open PRs must not be presented as production capability.
- Agent and UI operations share durable domain state. Credentials, publication, destructive changes, permission changes, and external side effects remain governed and auditable.
- Plugins and workflows declare versions, typed contracts, permissions, readiness, and failure semantics. Unknown, stale, unavailable, or unsafe capability bindings fail closed.
- Raw evidence and lineage survive cleaning, merging, retries, partial failure, workflow publication, and downstream export.
- Settings is the authoritative administration surface for import/export, migration history, compatibility reports, dependency repair, connection remapping, backup, and restore. Project pages may link into that surface but cannot create a parallel migration authority.

## Non-goals

- Operating a SaaS work-deployment or hosted data-processing platform.
- Becoming a generic chatbot, generic low-code builder, or infrastructure-topology product.
- Making external business delivery the core workflow; delivery remains an optional plugin or downstream consumer boundary.
- Treating the number of adapters, nodes, or catalog entries as proof of research quality.
- Recreating existing verified acquisition, workflow, MCP, evidence, or installation foundations under a parallel abstraction.
- Requiring operators to copy databases, edit package internals, recreate graphs, or transfer reusable credentials manually to move work between supported instances.

## Success signal

From a fresh local installation, an operator imports a project or workflow from another supported OpenCLI instance, resolves the reported local dependencies in Settings, and runs a persistent research project that acquires live multi-source information, produces a structured output with claim-level citations, and lets an external Agent traverse every citation to preserved source evidence through MCP or HTTP. Restarting or rerunning does not lose state or silently change the executed workflow version.

## Assumptions

- OpenCLI owns evidence-backed research outputs in addition to normalized evidence; the exact narrative-synthesis boundary still needs confirmation.
- OpenCLI and CloseI alignment means compatible capability and consumption contracts, not merging their product identities.

## Open Questions

- Must the first-party product produce final narrative conclusions, or only structured evidence packages and citation graphs for downstream Agents to synthesize?
- Should the primary Agent surface be a contextual global dock, a project-scoped workspace, or both?
- Which benchmark research journey and source set will be the release-level conformance test for CAP-1 through CAP-9?

