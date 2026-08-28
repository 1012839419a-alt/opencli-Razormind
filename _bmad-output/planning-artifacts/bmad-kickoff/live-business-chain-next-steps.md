---
name: gaojixing-live-business-chain-next-steps
type: execution-plan
status: derived-from-existing-openspec-tasks
created: 2026-08-27
normative-task-ledger: openspec/changes/gaojixing-live-business-chain/tasks.md
---

# Gaojixing Live Business Chain — Next Execution Plan

This is a dependency order for the **existing unchecked OpenSpec task IDs**. It neither edits task wording/status nor creates a parallel backlog. The OpenSpec task ledger remains authoritative. [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L25-L39)

## Stage 0 — Establish live-operability evidence (not a new OpenSpec task)

Before any live acceptance, inspect the seven operator-reported `running` runs and bind current evidence for Doubao session, Chrome pool capacity, network policy, and ODP `NOGROUP` to the affected run/resource. Use `external-prerequisites-and-ack-matrix.md`; any absent observation stays blocked/unknown. This is a sequencing prerequisite derived from the OpenSpec’s external-gate rule, not a change to its ledger. [OpenSpec proposal](../../../openspec/changes/gaojixing-live-business-chain/proposal.md#L36-L46)

## Stage 1 — Close the non-live boundary first

1. **4.1** — Label every fixture/mock run and artifact with mode/provenance and prevent it satisfying live acceptance.
2. **4.2** — Remove or reject implicit fallback when live capability, session, network, answer, or destination ACK is unavailable.
3. **4.3** — Add explicit fixture-only contract coverage for digest, evidence shape, lineage, and split transport/business outcome.

Why first: deterministic contracts establish the negative boundary that all live verification depends upon; the spec forbids fixture/mock fallback and demands explicit non-live reporting. [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L25-L29) [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L73-L84)

## Stage 2 — Verify gates and safety properties without asserting live success

4. **5.1** — Verify precise blockers for adapter, authentication, session health, and network permission.
5. **5.4** — Verify fixture/mock output is visibly non-live and cannot produce live business acceptance.
6. **5.6** — Verify timeout, CAPTCHA, unauthenticated session, network denial, empty/malformed evidence, lineage mismatch, and destination failure fail closed with typed state.
7. **5.2** — Verify one immutable snapshot/digest flows through answer, citation, conversation, record, evidence, and delivery projections.
8. **5.3** — Verify post-dispatch source changes cannot alter the captured snapshot/digest or mix run evidence.
9. **5.5** — Verify accepted transport without matching ACK remains unconfirmed/unknown; verify matching ACK confirms business outcome.

This order proves refusal/mode boundaries before happy-path lineage and then the ACK boundary. It implements the OpenSpec’s fail-closed and no-HTTP-202-as-success requirements. [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L31-L38) [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L60-L71) [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L86-L110)

## Stage 3 — Focused checks, then conditional live acceptance

10. **5.7** — Run focused contract/integration checks. Run a live acceptance only after all matrix prerequisites are actually observed and the destination ACK evidence is bound to the delivery attempt.

Do not convert a historical run, a fixture/mock, local fixture network result, `HTTP 202`, accepted transport, or no-error response into current business success. The relevant PTT evidence explicitly limits local fixture execution to adapter/kernel path evidence rather than internet/public acceptance. [OpenSpec tasks](../../../openspec/changes/gaojixing-live-business-chain/tasks.md#L38-L39) [OpenSpec proposal](../../../openspec/changes/gaojixing-live-business-chain/proposal.md#L40-L46) [PTT acceptance](../../../docs/ptt-acceptance.md#L197-L211)

## Completion rule

Do not mark this change live-accepted merely because tasks 1–3 are already checked or fixture checks pass. The final acceptance record must retain observed prerequisites and the matching destination ACK; otherwise retain the exact blocked/failed/partial/unconfirmed/unknown/fixture state. [OpenSpec spec](../../../openspec/changes/gaojixing-live-business-chain/specs/gaojixing-live-business-chain/spec.md#L99-L110)
