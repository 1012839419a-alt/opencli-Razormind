---
name: snailfish-bmad-kickoff-context
type: project-context
status: current-snapshot
created: 2026-08-27
source-of-truth: openspec/changes/gaojixing-live-business-chain/
---

# BMAD Kickoff — Current Project Context

## Authority and scope

`openspec/changes/gaojixing-live-business-chain/` remains the normative change contract: its proposal, requirements, and task checkboxes are not superseded or edited by this document. This is a BMAD orientation artifact that organizes the present Gaojixing slice for execution. The existing runtime PRD and ADRs remain supporting product and architecture records.

- The change defines an attributable live question-to-business-outcome chain, not a channel demo. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L1-L3)
- The product architecture keeps `WorkflowProject` as the authored execution input, compiles it in the backend, routes high-concurrency work to III/OpenCLI, and extends rather than rewrites the existing browser pool and ODP path. [Runtime PRD](../../../docs/workflow-hda-demand-runtime-PRD.md#L72-L91)
- A workflow runtime is evidenced by registry declaration, executable fixture, and observed run-event transcript; a fixture alone is not a live-delivery proof. [Runtime conformance](../../../docs/workflow-runtime-conformance.md#L3-L6) [Runtime conformance](../../../docs/workflow-runtime-conformance.md#L39-L42)

## OpenSpec-derived implementation position

| Area | Recorded position | Basis |
| --- | --- | --- |
| Contract | Tasks 1.1–1.4 are checked: immutable package/digest, independently attributable evidence, lineage, explicit fixture separation, and fail-closed blockers are specified. | [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L1-L6) |
| Capability and capture | Tasks 2.1–2.5 are checked. The repository has a `chat-ai.capture` live-mode Gaojixing runtime that hashes a canonical question package and rejects unavailable capability, denied network, or unhealthy Doubao session with typed errors. This is implementation evidence, not a live-acceptance receipt. | [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L8-L14) [Runtime gates](../../../backend/workflow/gaojixing_runtime.py#L46-L93) [Runtime gates](../../../backend/workflow/gaojixing_runtime.py#L96-L148) |
| Normalize, record, delivery | Tasks 3.1–3.6 are checked. The contract requires `source → normalize → accept → sink`, retained lineage, and separate transport from business outcome. | [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L16-L23) [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L47-L71) |
| Remaining scope | Tasks 4.1–4.3 and 5.1–5.7 are unchecked. Their execution and evidence—not the checked status of predecessor tasks—determine whether the change can close. | [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L25-L39) |

## Live versus deterministic boundary

- A live claim requires distinct observed capability publication, executable adapter/live mode, authenticated persistent session, passing session health, and permitted network; a catalog entry or configured channel is insufficient. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L7-L19)
- Every fixture/mock artifact must carry non-live mode and provenance, be excluded from live acceptance, and never be a fallback for a disappeared live dependency. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L73-L84)
- URL extraction is not citation verification; an unavailable conversation reference stays `unknown`. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L34-L45)
- HTTP `202`, enqueue acceptance, or no error is transport evidence only. Business success requires an ACK/equivalent tied to the delivery identity and lineage. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L60-L71) [ADR-0021](../../../docs/adr/0021-delivery-separates-submission-from-business-outcome.md#L3-L13)

## Known runtime blockers at kickoff

The following are **operator-reported current observations supplied for this kickoff**, not facts proved by a repository document and not grounds for a success claim: seven runs are `running`; the Doubao session and Chrome pool require current health/capacity evidence; and ODP reports `NOGROUP`. Preserve each as `blocked` or `unknown` until a run-scoped receipt identifies the resource, time, and typed state.

| Observation | Required treatment | Repository grounding for the treatment |
| --- | --- | --- |
| 7 running runs | Do not infer capacity, progress, or completion; obtain per-run event/status evidence and retain the run identity. | Run lifecycle state must be observable; runtime conformance uses the run events surface as evidence. [Runtime PRD](../../../docs/workflow-hda-demand-runtime-PRD.md#L87-L90) [Runtime conformance](../../../docs/workflow-runtime-conformance.md#L3-L6) |
| Doubao session | Re-run the immediate pre-execution health/identity gate; `unavailable`/CAPTCHA is a typed fail-closed outcome, not a fixture substitute. | [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L10-L14) [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L7-L19) |
| Chrome pool | Record actual pool/resource status before scheduling browser-bound work; do not treat a configured pool as available capacity. | Browser capacity is a resource pool. [Runtime PRD](../../../docs/workflow-hda-demand-runtime-PRD.md#L81-L85) |
| ODP `NOGROUP` | Capture stream/group and whether the group is absent; it is an explicit no-group condition, distinct from a Redis outage, and must not be hidden by a generic healthy result. | [ODP metrics](../../../backend/control/collectors/odp_metrics.py#L157-L182) |

## BMAD routing

This kickoff has completed the prerequisites for a feature-level architecture spine and an execution-oriented task plan. The next required work is the unchecked OpenSpec task sequence in `live-business-chain-next-steps.md`; do not create a parallel PRD, spec, epic list, or replacement task ledger.
