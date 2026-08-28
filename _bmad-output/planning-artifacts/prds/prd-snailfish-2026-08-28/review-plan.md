# Reviewer Gate Plan — Gaojixing Live Business Chain

Status: plan written; execution pending
Model/executor: OMP 5.6 Luna via Orca
Workspace: `_bmad-output/planning-artifacts/prds/prd-snailfish-2026-08-28/`

## Review inputs

Reviewers read and source-extract:

- `prd.md`
- `addendum.md`
- `reconcile-gaojixing-normative.md`
- `reconcile-opencli-emacs-article.md`
- `reconcile-opencli-website.md`
- `.memlog.md` — decision consistency only; not a product-requirement source and not a substitute for PRD/addendum evidence

No reviewer may modify `prd.md`, `addendum.md`, source inputs, or code.

## Reviewers

### `rubric-walker`

**Goal:** Judge the PRD against the complete seven-dimension quality rubric at high rigor for an internal production system.

**Checks:** decision-readiness and honest trade-offs; substance over persona/innovation/NFR/vision theater; strategic coherence of P1/S1/OODA/geoXI scope and metrics; testable done-ness of FRs/NFRs/UJs/metrics; scope honesty and deferred P2/P3 boundaries; downstream usability, glossary and cross-reference consistency; shape fit for a brownfield internal platform; mechanical ID continuity, assumptions, named protagonists, and required sections.

**Output:** `review-rubric.md`

### `adversarial-live-boundary`

**Goal:** Attack the production trust boundary and find plausible paths to false success.

**Checks:** readiness gate aggregation and unknown/blocked/ready semantics; live versus fixture/mock separation; execution status versus business outcome; immutable keyword package and lineage; evidence completeness and citation/conversation provenance; transport accepted versus geoXI consumed versus OODA cycle completed; matching receipt and project isolation; retry/idempotency and duplicate side effects; OODA risk-tier approvals; S1 candidate/under-review/known-good and rollback controls; fail-closed behavior and counter-metrics; whether repository evidence is incorrectly treated as live proof.

**Output:** `review-adversarial-live-boundary.md`

### `operational-acceptance`

**Goal:** Determine whether the PRD can guide observable acceptance across roles and real operations without inventing implementation contracts.

**Checks:** real-time and scheduled keyword journeys; schedule ±1 minute/99% definition, denominator, blocker treatment; real-time and geoXI latency baseline rules; seven-day/two-project/keyword-strata/100-live-cycle baseline sample; OODA 95% denominator and completion semantics; geoXI downstream responsibility and minimum receipt observability; role permissions and risk-tier intervention; evidence/lineage/receipt visibility; S1 trace/correction/version/approval journey; NFR measurability and counter-metrics; remaining phase-blocking ambiguity.

**Output:** `review-operational-acceptance.md`

## Output contract

Each reviewer writes only to its assigned `review-<slug>.md` and returns a compact summary. The file format MUST include:

- Overall verdict (`strong`, `adequate`, `thin`, or `broken`, as applicable)
- Findings grouped by severity: `critical`, `high`, `medium`, `low`
- Specific evidence anchors (PRD section/FR/NFR/UJ/metric and, where relevant, reconcile or addendum path)
- Recommended disposition for every finding: autofix, user decision, defer with owner/condition, or ignore with rationale

Findings must be about product quality and acceptance; implementation code/API/schema suggestions are out of scope.

## Execution orchestration

Because Orca worker count is constrained:

1. **Batch 1, parallel:** `rubric-walker` and `adversarial-live-boundary`.
2. **Batch 2, after Batch 1 settles:** `operational-acceptance`.

Each reviewer receives an isolated context containing the review inputs and this output contract. They do not coordinate through mutable PRD files, do not edit PRD/addendum/code, and do not run project-wide validation.

## Acceptance gate

Before finding resolution:

- Confirm all three review files exist at the exact output paths.
- Every critical/high finding has a concrete PRD anchor and a repair recommendation.
- Reject or reframe any recommendation that pollutes the review with implementation code/API/schema design.
- Collect all three compact summaries before opening finding resolution.

## Finding resolution plan

1. Deduplicate overlapping findings while preserving the strongest evidence anchor.
2. Resolve critical/high findings one at a time: obtain a user decision or apply only a safe, scope-preserving autofix.
3. Record medium/low findings with disposition, owner, and revisit condition where applicable.
4. Append every accepted change, decision, deferral, or override to `.memlog.md`.
5. An unresolved critical finding blocks polish and finalization; high findings require explicit disposition before polish.

## Subsequent Finalize sequence

After all findings are resolved or explicitly dispositioned:

1. Open-item triage.
2. Apply `skill:bmad-review lenses=structure,prose` in the declared document-standards order.
3. Set `prd.md` status to `final` and update the final date.
4. Append the finalized event to `.memlog.md`.

This file records planning only. Reviewer execution is pending and is not performed by this plan-writing step.
