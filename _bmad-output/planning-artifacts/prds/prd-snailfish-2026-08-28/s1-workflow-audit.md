# S1 Skill Workflow Contract Audit

只读审计；未修改 PRD/code，未运行测试。范围聚焦现有 skill API/UI/correction/distillation/evidence 合同及相关 OpenSpec/tests/docs。

## 1. 实际 lifecycle map

```text
record (Skill row/elements/source trace)
  -> distill (initial skill fields)
  -> execute (skill-channel self-eval appends executed evidence)
  -> failure trace (trace_id/loop outcome/passed)
  -> 3 eligible consecutive failures
  -> correction_proposed (flag only; never auto-redistill)
  -> human redistill from most recent supplied trace
  -> corrected, version n -> n+1 (body replaced; prior body stashed)
  -> execute new version
  -> rollback latest corrected version
  -> rolled_back, restore prior body/version
```

Correction proposal is deliberately not execution: `maybe_propose_correction` appends a marker; dock/endpoint triggers `re_distill`. Rollback is only for the latest corrected entry and rejects double rollback.

## 2. Current observable evidence, roles, actions

| Stage | Observable evidence / status | Role/action | Anchors | Contract status |
|---|---|---|---|---|
| Record/list/detail | Skill brief/detail includes version, model/source fields, evidence log; UI has `/skills` and `/skills/:id`. | Users view skills. | `backend/api/v1/skills.py:38-117`; `frontend/app/(app)/skills/page.tsx`; `frontend/app/(app)/skills/[id]/page.tsx` | Implemented read surface |
| Distill | `re_distill` accepts one/list trace, uses latest list entry, resolves provider, calls distill kernel, replaces body/elements/model/source trace, increments version. | Human correction trigger; endpoint/dock. | `backend/skills/correction.py:67-156`; `backend/api/v1/skills.py:154-201` | Implemented |
| Execute | Skill channel self-eval records `executed`, `passed`, trace and loop outcome; failure streak ignores `loop_outcome=error`. | Runtime executes; system appends evidence. | `backend/skills/correction.py:244-306`; `backend/skills/*`; tests `tests/integration/test_skills_api.py`, `tests/skills/test_skill_channel.py` | Implemented evidence contract |
| Failure/proposal | Three consecutive eligible failures since last corrected/dismissed boundary produce one `correction_proposed`; no duplicate open proposals. | System proposes; human reviews. | `correction.py:227-306`; UI detail openProposal mirror lines 64-78 | Implemented conservative trigger |
| Correction | `corrected` records from/to versions, trace id, timestamp, prior body/model/source snapshot. | Maintainer/human invokes redistill; no auto self-healing. | `correction.py:111-150`; PRD FR-017–022 | Implemented, but production authorization is not evidenced by this function |
| Rollback | Restores stashed previous fields, decrements to prior version, appends `rolled_back`; refuses absent/latest-already-rolled-back. | UI rollback action; API authoritative on stale read. | `correction.py:159-212`; `backend/api/v1/skills.py:139-151`; UI lines 81-97 | Implemented mechanical rollback |
| Dismiss | `correction_dismissed` resets streak boundary; UI/API exposes dismiss. | Human operator says failures not actionable. | `skills.py:120-136`; correction boundary lines 230-241 | Implemented |
| Production/known-good | UI/API vocabulary and PRD distinguish candidate/under-review/known-good, but audited correction code has no demonstrated promotion, approval, production enablement, or rollback-effectiveness state. | PRD assigns maintainer propose, admin approve. | `prd.md` FR-019–022; `correction.py` | Mostly declared, not evidenced |

## 3. Existing known-good / production / rollback semantics

**Existing facts:** version is monotonic for redistill and restored on rollback; evidence is append-only; prior body is stashed before overwrite; latest-only and no-double-rollback guards exist; correction proposal is human-triggered rather than automatic. The UI explicitly treats backend as authoritative for stale reads.

**Not evidenced:** a durable `known-good` promotion workflow, production enablement approval, role enforcement in the endpoint itself, representative real-success requirement, rollback approval, post-rollback execution proof, or a state proving the restored version is actually serving production runs. The endpoint signatures shown are DB-dependent and do not establish actor authorization.

Thus PRD FR-019–022 are new product commitments beyond the demonstrated lifecycle. OpenSpec/reconciliation also says checked task/implementation evidence is not live acceptance evidence.

## 4. T-H5 minimum evidence breadth safely derivable

A conservative minimum can be derived without asking the user:

1. The exact skill version and source trace must be identified for every execution.
2. The evidence must include the failed execution trace(s), failure stage/loop outcome, and whether the failure was environment noise or a skill failure (the existing proposal logic already excludes `loop_outcome=error`).
3. A correction must record from-version, to-version, trace id, timestamp, and the prior body/source snapshot (already implemented).
4. A proposed correction must be distinguishable from an executed correction; no proposal may silently promote or enable a version.
5. Before calling a version known-good, evidence must show at least one target-scope real execution that passed, with its trace/evidence linked to that exact version; fixture/mock or mere distillation cannot qualify (directly follows PRD authenticity and current evidence separation).
6. Rollback must identify the corrected version, restore the prior version, append an auditable event, and make double rollback impossible (existing invariant).
7. Candidate/under-review/known-good/rolled-back states must remain distinct and visible.

This is the minimum evidence breadth, not an invented sample-size policy.

## 5. Rollback effectiveness as observable product behavior

Express effectiveness as a user-verifiable outcome, not an internal operation: after an approved rollback, the skill detail and subsequent run trace show the prior version as the active version; the corrected version remains in history as rolled back; the next target-scope execution is attributable to the restored version; its outcome and failure trace (if any) are visible; and the system does not label the rollback successful merely because the database mutation completed. If the restored version cannot execute or its outcome is unknown, status stays blocked/unknown/failed and production trust is not restored.

## 6. Exact sample count / risk strata

The repository provides no basis for an exact number of known-good runs, domains, boundary cases, or risk strata. The PRD’s “at least one real success” is a product commitment, not an existing implementation fact. **Conservative defer:** assign the exact breadth to the platform administrator + skill maintainer / OODA strategy owner, conditioned on target capability risk and real target-scope evidence being available; until decided, do not claim known-good beyond the minimum one linked real pass and keep the version under review. No need to ask for a number during this audit.

## 7. Recommended T-H5 resolution patch plan (no implementation design)

1. Preserve current safe mechanics: proposal-only trigger, environment-error exclusion, append-only evidence, exact version transitions, prior-body rollback snapshot, latest-only rollback.
2. Add product language that every execution/approval/correction/rollback is tied to an explicit skill version and linked trace evidence.
3. State that `candidate`, `under-review`, `known-good`, and `rolled-back` are mutually non-interchangeable; proposal or distillation never promotes a version.
4. Adopt the derived minimum breadth above: one target-scope real passing execution with complete linked evidence is the provisional floor; fixtures, mocks, catalog state, and repository/task completion cannot qualify.
5. Define rollback success by observed post-rollback active version plus attributable follow-up execution outcome, not by mutation completion.
6. Defer exact sample count/risk strata to named operational owners and record the condition for revisiting; do not invent a number.
7. Require production enablement/rollback approval to be visible and auditable, while leaving actor/permission implementation out of this product-semantic patch.

**Unique question that genuinely remains:** What minimum real-success breadth (sample count and risk strata) should the business require before a skill version is promoted to `known-good` for production? Everything else above can be resolved conservatively from existing contracts and observed invariants.
