# Reconciliation — Gaojixing normative/repository inputs

Against: `prd.md` + `addendum.md`
Date: 2026-08-28
Mode: extraction only; no PRD/addendum/code changes

## `openspec/changes/gaojixing-live-business-chain/proposal.md`

- **Gap — live acceptance prerequisites:** The proposal requires published executable live capability, authenticated healthy Doubao session, permitted network, reachable destination with documented acknowledgement, and an operator-owned immutable package. The PRD carries these as dependencies/readiness, but the destination acknowledgement contract remains intentionally product-level and unresolved in repository fact.
- **Gap — non-goal boundary:** The proposal explicitly does not claim current capability publication, live session, public network access, or destination ACK. PRD language should continue to distinguish intended acceptance from current proof.
- **Semantic preservation:** Immutable package/digest, independent answer/citation/conversation evidence, lineage, fail-closed behavior, fixture separation, and transport/business outcome separation are represented. No implementation fact should be promoted to completed live acceptance.

## `openspec/changes/gaojixing-live-business-chain/tasks.md`

- **Gap — verification remains incomplete:** Tasks 4.1–4.3 (fixture/mock labeling, no implicit fallback, fixture-only coverage) and 5.1–5.7 (readiness, immutable lineage, fixture exclusion, ACK semantics, fail-closed cases, focused/live acceptance) are unchecked. The PRD’s requirements and metrics must not imply those tasks are delivered.
- **Gap — implementation status versus product commitment:** Tasks 1.1–3.6 are checked, but checked task definitions are contract/implementation ledger evidence, not proof of an observed live run or destination consumption.
- **Semantic preservation:** Replay without another provider call, canonical dedupe, retry lineage, typed blockers, and no HTTP-202-as-business-success are retained in PRD requirements or boundaries.

## `openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md`

- **Gap — receipt/geoXI detail:** The spec requires a documented destination ACK/equivalent tied to delivery identity, but does not define geoXI-specific receipt fields or consumer event semantics. Current PRD intentionally records the agreed minimum observable receipt at product level without inventing a schema/API.
- **Gap — evidence verification:** Citation extraction is not citation verification; unavailable conversation identity remains unknown/null. This distinction must remain visible in product language and acceptance review.
- **Gap — state separation:** Readiness, execution mode/status, transport, business outcome, and OODA completion must not collapse into one success state; fixture/mock output is excluded from live acceptance.

## `_bmad-output/planning-artifacts/bmad-kickoff/current-project-context.md`

- **Gap — operator observations are not repository proof:** Seven running runs, Doubao session/Chrome pool health needs, and ODP `NOGROUP` are operator-reported kickoff observations. They must remain blocked/unknown until run-scoped receipts exist.
- **Gap — current capability evidence:** Existing runtime/fixture evidence is implementation evidence, not a live-acceptance receipt; no claim of live success should be inferred.
- **Semantic preservation:** WorkflowProject/backend compiler/III/OpenCLI reuse and source→normalize→accept→sink are architecture context, not a new parallel executor or backend rewrite.

## `_bmad-output/planning-artifacts/bmad-kickoff/external-prerequisites-and-ack-matrix.md`

- **Gap — gate observation:** Capability publication, session identity/health, Chrome capacity, network policy, immutable input, capture evidence, lineage, transport, destination ACK, and ODP group health each require fresh run-scoped observations; the PRD has requirements and baseline plans but no such receipt.
- **Gap — explicit non-evidence:** Catalog metadata, configured channels/pools, historic login, HTTP 202/enqueue success, URL extraction, fixture output, and aggregate running counts cannot satisfy live acceptance.
- **Semantic preservation:** Missing or contradictory observations remain precise blocked/unknown/failed/partial/unconfirmed states, never silently successful.

## `_bmad-output/planning-artifacts/bmad-kickoff/live-business-chain-next-steps.md`

- **Gap — execution sequence is not delivery:** The plan prioritizes fixture boundary (4.x), then gate/safety verification (5.1/5.4/5.6), lineage/immutability (5.2/5.3), ACK boundary (5.5), and focused/live acceptance (5.7). The PRD should not represent this dependency order as completed work.
- **Gap — Stage 0 blockers:** Fresh evidence for the seven running runs, Doubao session, Chrome pool, network policy, and ODP `NOGROUP` precedes live acceptance; these are not replaced by deterministic tests.
- **Semantic preservation:** Historical runs, local fixtures, accepted transport, or no-error responses cannot be promoted to current business success.

## `docs/workflow-hda-demand-runtime-PRD.md`

- **Gap — existing platform surface versus Gaojixing outcome:** This PRD establishes WorkflowProject as authoring/execution source of truth, backend compilation, III/OpenCLI execution, browser-pool reuse, and projection surfaces; it does not prove Gaojixing live capture or geoXI consumption.
- **Gap — user-facing product intent:** Canvas/HDA/package nodes, AI structured patches, node-level progress, and evidence/cluster projections are platform affordances. The Gaojixing PRD should preserve the platform-entry intent without claiming a new UI or implementation.
- **Semantic preservation:** No backend rewrite, no parallel executor, and no raw OpenCLI/III payload authoring by AI remain consistent with current scope.

## `docs/adr/0009-plan-ir-free-graph-two-tier-attribution.md`

- **Gap — attribution is architecture guidance:** Backend-authoritative graph compilation and source-keyed/two-tier attribution guide lineage, but ADR evidence does not establish geoXI receipt or business confirmation.
- **Gap — product observable boundary:** The PRD must express attributable project/source/run/artifact outcomes without exposing ADR implementation mechanisms as user commitments.
- **Semantic preservation:** One authored WorkflowProject graph and preserved source/run attribution are consistent with the PRD’s lineage requirements.

## `docs/adr/0021-delivery-separates-submission-from-business-outcome.md`

- **Gap — destination policy remains open:** The ADR establishes that transport/execution result and business outcome are distinct, with destination policy governing callbacks, status queries, retries, compensation, or human confirmation. It does not define geoXI’s concrete receipt contract.
- **Gap — pending outcome behavior:** Unknown/pending outcomes need not universally block workflows; the product must distinguish safe continuation policy from business confirmation. Current PRD fail-closed rules apply to evidence/lineage/receipt anomalies and do not turn transport acceptance into confirmation.
- **Semantic preservation:** Agent actions cannot declare business success without outcome evidence; human review remains a valid escalation path.

## Cross-input reconciliation summary

- No source contradicts the platform vision, P1 internal entry focus, S1 scope, system-owned OODA, keyword collection, or geoXI downstream-product decision.
- The main semantic risk is treating checked tasks, fixture/runtime evidence, catalog/configuration, transport acceptance, or historical/operator observations as live business acceptance.
- The principal unresolved product contract is the user-observable geoXI consumption receipt and responsibility boundary; current PRD contains the agreed product-level minimum, while repository sources do not define a technical schema/API.
- The PRD’s current baseline contract (two projects, keyword strata, real-time + scheduled, seven days, at least 100 live OODA cycles, stratified reporting, blockers separately reported) is a later product decision and is not asserted by these normative sources.
