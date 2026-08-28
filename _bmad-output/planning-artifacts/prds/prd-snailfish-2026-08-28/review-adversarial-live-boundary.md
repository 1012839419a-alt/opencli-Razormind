# PRD Reviewer Gate — adversarial-live-boundary

## Overall verdict

**thin** — The PRD states the intended trust boundary unusually clearly, but several acceptance semantics remain underspecified at the exact points where a production system can manufacture a successful-looking result. The missing controls are not implementation details; they determine whether a displayed state is admissible as live business success.

## Critical findings

### C-1 — Readiness aggregation can certify stale or mixed-time evidence
- **Anchor:** FR-004–FR-005 (lines 93–97), Current Release Scope readiness (lines 39–41).
- **Why false success is possible:** The rule says how to aggregate gate states but not evidence freshness, run identity, or whether all gates were observed from one coherent evaluation. A previously healthy session/browser gate can be combined with a current failed network or runtime-binding condition, yielding `ready` for a run that cannot actually execute live.
- **Recommended disposition:** **autofix** — define freshness/expiry and atomic, run-scoped gate evaluation; stale or mixed evaluations must remain unknown/blocked.

### C-2 — `ready` is not bound to a specific live admission decision
- **Anchor:** FR-009 (lines 109–116), FR-023 (lines 166–168), FR-027 (lines 178–179).
- **Why false success is possible:** A capability can be ready when the user opens the page but lose authentication, Chrome capacity, or network permission before admission. The PRD does not require a final gate check tied to the exact collection/run, so the UI can show a run as admitted/live based on an obsolete readiness snapshot.
- **Recommended disposition:** **autofix** — require an explicit run-scoped admission observation and preserve its identity in the resulting state.

### C-3 — Immutable keyword package is required, but package integrity is not an acceptance condition
- **Anchor:** FR-011 (lines 122–123), FR-025 (lines 170–174), NFR-001/NFR-004 (lines 276–286).
- **Why false success is possible:** “不可变” and “一致性标识” do not say what happens when the stored package, digest, expansion, or supplied package disagrees at execution, retry, delivery, or receipt time. A result may be attributed to the displayed package while the actual query set changed.
- **Recommended disposition:** **autofix** — make package identity/integrity mismatch an explicit blocked/failed condition at every boundary, including retries.

### C-4 — Citation capture and conversation evidence can pass without proving answer provenance
- **Anchor:** FR-012–FR-013 (lines 125–129), FR-029–FR-030 (lines 185–193).
- **Why false success is possible:** The PRD correctly distinguishes URL extraction from citation verification, but defines no minimum acceptance rule for verified citation, answer-to-citation linkage, or conversation/session continuity. An answer with unrelated URLs or an unavailable conversation can therefore progress through normalize/accept while still appearing evidence-backed.
- **Recommended disposition:** **user decision** — decide the minimum evidence completeness required for acceptance versus merely displayable/partial output; then state that rule explicitly.

## High findings

### H-1 — Transport/consumption states lack a terminal timeout and stale-receipt policy
- **Anchor:** FR-014–FR-016 (lines 131–138), FR-033–FR-035 (lines 200–206).
- **Why false success is possible:** `accepted`, `consumed`, and `confirmed` are separated, but no deadline or terminal transition is defined for a missing, delayed, superseded, or never-arriving receipt. Operators may treat a permanently pending delivery as operational success, or a late receipt may confirm the wrong historical attempt.
- **Recommended disposition:** **user decision** — define pending/expired semantics and receipt validity window before calling an outcome confirmed.

### H-2 — Receipt matching does not state anti-replay or authenticity requirements
- **Anchor:** FR-015 and FR-033 (lines 134–135, 199–200), NFR-002 (lines 279–280).
- **Why false success is possible:** Matching fields can be copied, duplicated, replayed, or associated with a prior attempt unless uniqueness, provenance, and duplicate/replay handling are acceptance rules. A stale receipt for the same project/package can falsely confirm a new delivery.
- **Recommended disposition:** **autofix** — require receipt uniqueness and explicit rejection of replay/duplicate/ambiguous receipts as unconfirmed.

### H-3 — Project isolation is a principle, not a demonstrated boundary at every join
- **Anchor:** NFR-004 (lines 285–286), FR-015/FR-033 (lines 134–135, 199–200), UJ-003 (lines 262–264).
- **Why false success is possible:** The requirement says records “不得跨项目混用” but does not require project identity to be checked independently at package, run, delivery, receipt, and persisted-result joins. A valid receipt from project A could be accepted for project B if the UI or association layer chooses the wrong context.
- **Recommended disposition:** **autofix** — make every association mismatch observable and fail closed; include cross-project negative acceptance cases.

### H-4 — Retry/idempotency coverage omits concurrent and ambiguous outcome cases
- **Anchor:** FR-036 (lines 208–209), NFR-001 (lines 276–277), Authenticity guardrail metric (lines 239–243).
- **Why false success is possible:** “不得产生重复业务结果” does not specify behavior after timeout-after-send, consumer rejection after transport acceptance, concurrent retries, or unknown receipt status. A retry can create two geoXI records while only one is displayed, or a duplicate can be hidden by dedupe and counted as success.
- **Recommended disposition:** **autofix** — require observable attempt-level reconciliation for ambiguous and concurrent retries; duplicates must remain incidents and cannot improve success rates.

### H-5 — OODA risk-tier approvals are not tied to a concrete decision instance or policy version
- **Anchor:** Product Principle 6 (lines 32–34), FR-031–FR-032 (lines 194–198), NFR-003 (lines 282–283).
- **Why false success is possible:** “Low/medium/high” is named, but there is no required record of who approved which exact action, under which policy, with what evidence, expiry, or scope. A broad prior approval could be reused for a changed keyword range, target project, or skill version.
- **Recommended disposition:** **user decision** — define approval scope, freshness, actor accountability, and what evidence is frozen for the decision; avoid accepting a generic approval as authorization.

### H-6 — S1 known-good can be promoted after one success despite untested rollback and boundary cases
- **Anchor:** FR-019–FR-022 (lines 150–160), UJ-005 (lines 270–272).
- **Why false success is possible:** “At least once” real success plus complete trace does not require success under relevant boundary inputs, receipt confirmation, rollback rehearsal, or absence of latent duplicate effects. A candidate can become known-good after a lucky run and then be used as the trusted fallback.
- **Recommended disposition:** **user decision** — set the minimum evidence breadth and require rollback effectiveness evidence before known-good promotion.

### H-7 — Fail-closed rules do not prevent a partial result from being presented as a successful collection
- **Anchor:** FR-016, FR-026–FR-027 (lines 137–138, 175–179), UJ-001/UJ-002 (lines 254–260).
- **Why false success is possible:** The PRD lists empty, stale, timeout, source-change, evidence, and destination failures, but does not define whether partial keyword/page/session coverage may be accepted. A run can be “completed” for some work and still be interpreted as a complete live collection.
- **Recommended disposition:** **user decision** — decide partial-coverage semantics and require explicit completeness/coverage state before any collection-success claim.

### H-8 — Counter-metrics can still hide blocked work through the eligibility boundary
- **Anchor:** Scheduled metric denominator (lines 215–218), OODA metric denominator (lines 227–231), Counter-metrics (lines 245–250).
- **Why false success is possible:** “Eligible” and “explicitly declared external blocker” are not operationally defined. A system can classify authentication, capacity, receipt, or ODP failures as blockers and remove them from rates while reporting only a small blocked count, creating an inflated 95%/99% appearance.
- **Recommended disposition:** **autofix** — require immutable admission/eligibility classification, blocker taxonomy, and independent reconciliation of all triggered/enabled runs.

## Medium findings

### M-1 — Repository and checked-task evidence can still leak into product status
- **Anchor:** Addendum §4 (lines 54–58), reconcile-gaojixing-normative §1–§6 (especially lines 14–17, 27–35), PRD Dependencies & Risks (lines 297–300).
- **Why false success is possible:** The reconciliations warn that checked tasks, fixtures, catalog metadata, operator observations, and historic runs are not live proof, but the PRD has no explicit user-facing evidence provenance taxonomy. A reviewer or operator can still promote implementation evidence into a live acceptance badge.
- **Recommended disposition:** **autofix** — require every acceptance claim to label evidence class and prohibit repository/configuration evidence from satisfying live gates.

### M-2 — Live/fixture/mock separation is stated but source-of-truth precedence is undefined
- **Anchor:** FR-006–FR-007 (lines 99–103), Metrics lines 239–250.
- **Why false success is possible:** A run may begin live and fall back to fixture/mock after a provider or browser failure, or combine live answer data with fixture evidence. The PRD forbids silent fallback but does not define the final mode when mixed artifacts exist.
- **Recommended disposition:** **autofix** — define mixed-mode as non-live and non-acceptable for live outcomes; retain per-artifact provenance.

### M-3 — OODA completion can be recorded without proving feedback was causally consumed
- **Anchor:** FR-028, FR-034–FR-035 (lines 185–206).
- **Why false success is possible:** A cycle can record all four stage labels and a feedback status while feedback is empty, duplicated, late, or not used to influence the next decision. “Recorded” completion can therefore masquerade as a closed control loop.
- **Recommended disposition:** **user decision** — define the minimum valid feedback and causal linkage required for `cycle completed`; otherwise use a distinct partial/blocked state.

### M-4 — Scheduled-run identity and missed-run recovery are underspecified
- **Anchor:** FR-024–FR-026 (lines 169–176), NFR-007 (lines 294–295), scheduled metric (lines 213–218).
- **Why false success is possible:** A scheduler can trigger twice, skip a run, or execute a late run under a new package while reporting punctuality against the nominal schedule. Without a unique scheduled occurrence and explicit missed/coalesced semantics, both duplicate effects and inflated punctuality are possible.
- **Recommended disposition:** **autofix** — require occurrence identity and explicit accounting for skipped, coalesced, duplicate, and late triggers.

## Low findings

### L-1 — “Freshness” has no product-level meaning for answers, evidence, or receipts
- **Anchor:** FR-026 and FR-029 (lines 175–176, 188–189), NFR-006 (lines 291–292).
- **Why false success is possible:** Without a defined observation time/age boundary, stale but complete evidence can be displayed as current and support a new OODA decision.
- **Recommended disposition:** **defer with owner/condition** — define freshness during operational acceptance before live claims.

### L-2 — “可查询” persistence is asserted without specifying query visibility/consistency condition
- **Anchor:** FR-033–FR-034 (lines 199–203), UJ-003 (lines 262–264).
- **Why false success is possible:** A consumer receipt may arrive before the result is actually visible to the intended project users or query path; the UI can mark confirmed while the business record is not usable.
- **Recommended disposition:** **user decision** — define what observable queryability is sufficient for confirmation.

### L-3 — Pause semantics do not cover in-flight delivery or OODA actions
- **Anchor:** Users & Roles lines 47–49, 71–73; NFR-003 (lines 282–283); UJ-004 (lines 266–268).
- **Why false success is possible:** “Pause” may stop new runs while an already admitted Act continues across a risk or credential change, producing an unreviewed side effect that is later counted as successful.
- **Recommended disposition:** **defer with owner/condition** — clarify pause scope and status treatment for in-flight actions during operational acceptance.

### L-4 — Acceptance does not require clock/time-order integrity across run, delivery, and receipt
- **Anchor:** FR-011, FR-015, FR-033–FR-035 (lines 122–135, 199–206).
- **Why false success is possible:** A receipt with inconsistent timestamps or an event arriving out of order can be matched and shown as current despite belonging to an earlier run or future/replayed event.
- **Recommended disposition:** **defer with owner/condition** — make event ordering and timestamp anomalies explicit blocked/unconfirmed cases.
