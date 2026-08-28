# Workflow Contract Audit

只读盘点；未修改 PRD/addendum/code，未运行测试。结论基于仓库当前代码、OpenSpec 与已指定文档；geoXI 专属消费契约在仓库中不存在。

## 1. End-to-end workflow map

```text
Capability catalog/context
  -> readiness (declared gates; runtime has partial preflight)
  -> realtime or scheduled collection
  -> Observe (capture artifact)
  -> Orient (normalize/lineage/evidence; product-declared)
  -> Decide (risk policy/control contracts; product-declared)
  -> Act (webhook delivery)
  -> geoXI delivery/receipt (repo has generic destination ACK parsing only; geoXI contract absent)
  -> feedback/next cycle (OODA product commitment; no demonstrated geoXI loop)

S1: record -> distill -> execute -> failure trace/correction -> maintainer proposes rollback
   -> platform administrator approves production rollback/enablement -> known-good governance
```

## 2. Stage inventory

| Stage | Current implemented / declared behavior | Observable evidence / vocabulary | Anchors | Status |
|---|---|---|---|---|
| Capability/readiness | PRD defines eight independent gates and unknown/blocked/ready aggregation. Runtime checks capability id/availability, configured blockers, network permission, channel health; it does not implement the full aggregate gate model. | `GaojixingReadinessError` with typed codes; PRD gate states. | `prd.md` FR-002/004–007; `backend/workflow/gaojixing_runtime.py:107-161` | Partial implementation; declared broader product contract |
| Package | Runtime resolves question/options once, canonicalizes JSON, computes SHA-256 digest, freezes options. | `GaojixingQuestionPackage`, `digest`, `questionPackage`. | `gaojixing_runtime.py:38-104` | Implemented for one question package; PRD expands immutable run/package lineage |
| Live capture | Preflight then real `DoubaoResearchChannel`; explicitly never uses fixtures. | live/fixture/mock constants; channel health/readiness; answer item. | `gaojixing_runtime.py:16-25,107-161` | Implemented source boundary |
| Evidence | Capture mapping separates answer, citations, conversation. Citation `verified` is always false; conversation missing is `unknown`; URL extraction is not verification. | evidence schema; statuses `captured`, `unavailable`, `empty`, `unknown`; mode/provenance. | `gaojixing_runtime.py:164-232` | Implemented conservative evidence mapping |
| Normalize/lineage | Delivery context validates package/evidence mode/provenance and source lineage; mixed batch contexts fail. | `WorkflowWebhookDeliveryError` codes; lineage mismatch/context mismatch. | `webhook_delivery.py:152-263,291-343` | Implemented boundary checks; not full OODA |
| Transport Act | Generic webhook sends payload and reports `transportStatus=accepted` only when notifier returns delivered. Network/notifier failures are explicit. | `delivered`, `transportStatus`, `businessOutcome`. | `webhook_delivery.py:26-150` | Implemented transport, not geoXI consumption |
| Receipt/business outcome | Generic response parser recognizes `businessAck=true`, `business_ack=true`, `acknowledged=true`, or status confirmed/acknowledged; requires matching delivery id for live confirmation. | `ackEvidence`, `liveAccepted`, `confirmed/unconfirmed`. | `webhook_delivery.py:118-150,266-288` | Generic placeholder; not geoXI contract |
| OODA/feedback | PRD requires system-owned Observe/Orient/Decide/Act and feedback-linked next cycle. Control package provides policy/cycle/ledger/kill-switch concepts, but current evidence does not demonstrate Gaojixing end-to-end closure or geoXI feedback consumption. | PRD statuses; control module contracts; no geoXI receipt/event. | `prd.md` FR-028–036; `docs/SYSTEM_ANALYSIS.md`; `docs/CONTROL_THEORY_ARCHITECTURE.md`; `backend/control/*` | Declared product commitment, not proven live workflow |
| Schedule | Scheduling/automation surfaces exist and PRD defines enabled/unpaused ±1 minute, 99% metric. Audit evidence does not establish Gaojixing package/lineage/receipt semantics for scheduled occurrences. | schedule enabled/paused/next run/recent status are product needs. | `prd.md` FR-024–026/NFR-007 | Existing platform surface; Gaojixing contract gap |
| S1 correction/rollback | PRD declares trace, stages, candidate/under-review/known-good, maintainer proposal and administrator approval. Reconciled OpenSpec says this is trust/governance scope, not automatic self-healing/crystallization. | candidate, under-review, known-good, correction/rollback states. | `prd.md` FR-017–022; `openspec/.../spec.md`, `tasks.md` | Product contract; acceptance tasks remain incomplete |

## 3. Invariants directly adoptable (no user question)

1. Live capture must call the real Doubao channel and must never silently fall back to fixture/mock (`gaojixing_runtime.py:107-161`; PRD FR-006/007).
2. Missing effective question is a typed readiness blocker, not a successful empty run (`gaojixing_runtime.py:62-77`).
3. Package digest is canonicalized and frozen for the runtime package (`gaojixing_runtime.py:95-104`).
4. Answer, citation capture, and conversation evidence are independent; citation extraction is not verification and missing conversation remains unknown (`gaojixing_runtime.py:182-207`).
5. Delivery rejects incomplete, contradictory, or mixed Gaojixing source contexts and lineage (`webhook_delivery.py:179-237,291-343`).
6. Transport delivered/accepted is not business confirmation; live confirmation requires a response acknowledgement whose delivery id matches (`webhook_delivery.py:118-150,266-288`).
7. Fixture/mock cannot satisfy live acceptance; mode and provenance remain visible.
8. Repository checked tasks, fixtures, catalog/configuration, historical runs, and operator observations are not live proof (`reconcile-gaojixing-normative.md:13-17,25-35`; `addendum.md:54-58`).
9. geoXI is a downstream product, not a snailfish internal module; no geoXI technical contract may be invented (`addendum.md:54-58`).
10. S1 does not include automatic self-healing, general crystallization, dynamic loading, or a public plugin ecosystem (`addendum.md:5-19`).

## 4. PRD commitments beyond current facts

- Full eight-gate product readiness aggregation, freshness, and user-facing gate reasons.
- Realtime and scheduled immutable package lineage across complete runs.
- Product-level Orient/Decide/Act and feedback-linked next-cycle behavior owned by snailfish.
- Matching, persisted/queryable geoXI receipt as business confirmation, with project isolation.
- Risk-tier approval behavior for OODA actions.
- 100 live cycles over seven days across two real geoXI projects and keyword strata as baseline evidence.
- S1 known-good and rollback acceptance governance.
- 99% schedule punctuality and 95% complete system-owned OODA targets.

These are commitments, not implementation evidence. OpenSpec explicitly says acceptance tasks 4.x/5.x remain unchecked (`reconcile-gaojixing-normative.md:13-17`).

## 5. Reviewer T-H4/T-H5 and medium findings

### T-H4: retry/idempotency and duplicate side effects
**Safe derivation:** Existing delivery id is deterministic from workflow/run/node/package digest (`webhook_delivery.py:248-255`); lineage and mixed-context checks already fail closed; PRD NFR-001/FR-036 already prohibit duplicate outcomes. Therefore the PRD can be patched without user input to require attempt-level visibility, preserve the same identity on retry, and classify ambiguous timeout-after-send/concurrent retry as unconfirmed until reconciled. The current code does not prove downstream idempotency or duplicate prevention.

**Genuine business decision:** Whether an ambiguous transport may safely continue, how long to wait before expiry, and whether compensation/manual review is required are destination/business policies—not derivable from repo facts.

### T-H5: OODA risk approvals
**Safe derivation:** Existing control package has policy, gate, cycle, ledger, kill-switch, actuator, and operations-agent policy concepts; PRD already names role tiers. Patch can require every decision to retain its risk tier, decision evidence, actor, and approval state, and stop on evidence/lineage/receipt anomalies. This does not invent an API/schema.

**Genuine business decision:** Which specific actions are low versus medium/high risk, and approval expiry/scope for frequency, project, capability, or production skill changes, require the OODA/business owners.

### Medium findings
- **Stale/mixed readiness:** safe derivation from runtime preflight plus PRD gate semantics: require a run-scoped, fresh admission result; no user decision needed.
- **Repository evidence mistaken for live proof:** safe derivation from addendum/reconciliation; require evidence-class labeling and prohibit checked tasks/fixtures/configuration from satisfying live acceptance.
- **Mixed live/fixture artifacts:** safe derivation from explicit no-fallback invariant; any mixed-mode run is non-live and cannot confirm.
- **OODA completion without causal feedback:** genuine business decision on minimum valid feedback and whether a cycle may be complete without a next action.
- **Partial collection semantics:** genuine business decision on whether partial keyword coverage is usable, and what outcome label it receives.
- **Freshness and queryability:** business/operations decision for acceptable age and when a persisted result is truly queryable; geoXI contract is absent.

## 6. geoXI contract boundary

**Repo absent.** The repository contains no defined geoXI/GEO-XI-specific consumption contract, consumer event, ACK specification, persistence visibility guarantee, receipt freshness/expiry rule, or anti-replay rule. `webhook_delivery.py` only parses generic response fields and a matching delivery id. No geoXI behavior, receipt fields, or project persistence may be claimed from this code.

## 7. Concrete next PRD patch plan (product semantics only)

1. Add run-scoped readiness admission and evidence freshness; define stale/mixed gate behavior.
2. State immutable package mismatch, mixed mode, and lineage mismatch as explicit non-live terminal outcomes.
3. Add evidence-class/provenance labels separating repository, fixture, execution, and live business proof.
4. Clarify citation/conversation acceptance versus displayable partial evidence.
5. Add attempt-level retry semantics and ambiguous-send handling while retaining deterministic attribution.
6. Require risk decision records and approvals tied to the exact action/evidence; leave risk classification matrix to owner decision.
7. Define partial collection, OODA feedback sufficiency, and pending/expired destination outcome semantics.
8. Keep geoXI requirements at product boundary until geoXI owner supplies the real receipt/persistence contract; then add acceptance conditions without inventing fields.
9. Make baseline denominators auditable from all enabled/admitted occurrences, with blocker taxonomy and counter-metrics.
10. Strengthen S1 known-good/rollback acceptance with representative real evidence and explicit production approval.
