---
title: 'Neutralize Spreadsheet Formulas in CSV Exports'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
review_loop_iteration: 0
baseline_commit: '007ce78bd4c373f430b3607e935fef8f4b63a2b2'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The project data workbench writes untrusted collected values directly into CSV cells. Spreadsheet applications can interpret values beginning with formula markers as executable formulas when the exported file is opened.

**Approach:** Add a pure CSV-cell serializer that neutralizes formula-like text before applying standard CSV quoting, and use it only in the CSV export path. Preserve JSON and XLSX behavior.

## Boundaries & Constraints

**Always:** Treat collected record fields as untrusted. Neutralize formula markers after leading whitespace or control characters. Preserve valid CSV quoting, CRLF row separators, UTF-8 BOM, and the visible original value. Keep normal negative numeric literals usable as numbers. Add executable behavioral coverage for the serializer.

**Ask First:** Any change to JSON export structure, XLSX cell behavior, record projection, or exported column selection.

**Never:** Sanitize values in the on-screen table, mutate stored records, remove formula characters, rely on source-text regex assertions as the only test, or modify/revert unrelated dirty-tree changes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Formula marker | `=SUM(A1:A2)`, `+cmd`, or `@value` | CSV cell is prefixed with an apostrophe before quoting | N/A |
| Leading whitespace/control | spaces, tab, CR, or LF before a formula marker | Formula is still neutralized and quoting remains valid | N/A |
| Negative number | `-42`, `-1.5`, `-1e3` | Numeric text remains unchanged | N/A |
| Hyphenated prose | `- pending review` | Text is neutralized because it begins with a spreadsheet trigger | N/A |
| CSV metacharacters | comma, quote, CR, or LF | Cell is quoted and embedded quotes are doubled after neutralization | N/A |
| Non-formula text | ordinary text, empty string, dates, identifiers | Cell content is unchanged apart from required CSV quoting | N/A |

</frozen-after-approval>

## Code Map

- `frontend/app/(app)/studio/projects/[projectId]/data/page.tsx:474-510` -- sole CSV export path; invokes the new serializer at the final cell boundary. JSON and SheetJS branches are read-only boundaries.
- `frontend/lib/csv.ts` -- new pure, browser-safe helper for formula neutralization and RFC-style CSV cell quoting; no React or project aliases required.
- `frontend/scripts/check-project-workbench-regressions.mjs` -- focused `node:test` contract suite; add TypeScript loading hooks and executable serializer cases rather than source-only assertions.
- `frontend/scripts/check-record-relationship-regressions.mjs:1-38` -- reuse the repository's `registerHooks` plus `stripTypeScriptTypes` convention for importing pure TypeScript in Node tests.
- `frontend/package.json:5-22` -- existing Node test command conventions; no dependency addition required.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/lib/csv.ts` -- implement a pure CSV cell serializer covering neutralization and quoting at one boundary.
- [x] `frontend/app/(app)/studio/projects/[projectId]/data/page.tsx` -- replace inline CSV cell escaping with the helper without changing JSON or XLSX exports.
- [x] `frontend/scripts/check-project-workbench-regressions.mjs` -- execute formula, whitespace/control, numeric, hyphenated text, quoting, and ordinary-value cases.

**Acceptance Criteria:**
- Given untrusted collected data, when the user exports CSV, then spreadsheet formula triggers are neutralized without deleting or rewriting the original value.
- Given normal negative numeric literals, when CSV is generated, then their text remains unchanged.
- Given commas, quotes, CR, or LF, when CSV is generated, then the result remains valid quoted CSV.
- Given the same records exported as JSON or XLSX, when this fix is applied, then those branches remain unchanged.

## Spec Change Log

## Design Notes

Neutralize before quoting. Inspect the first non-whitespace/control character; prefix an apostrophe to the complete original text when it is `=`, `+`, `@`, or `-`, except for a strict negative-decimal/exponent literal. The apostrophe is intentionally retained in CSV bytes so spreadsheet software treats the cell as text.

## Verification

**Commands:**
- `cd frontend && node --test scripts/check-project-workbench-regressions.mjs` -- expected: executable CSV serializer cases and existing workbench contracts pass.
- `cd frontend && pnpm exec tsc --noEmit` -- expected: no diagnostics attributable to the changed source; report pre-existing generated `.next` route diagnostics separately if still present.

## Suggested Review Order

**CSV security boundary**

- Entry point applies hardening only to downloadable CSV cells.
  [`data/page.tsx:496`](../../frontend/app/(app)/studio/projects/%5BprojectId%5D/data/page.tsx#L496)

- Pure serializer neutralizes formulas before standard CSV quoting.
  [`csv.ts:1`](../../frontend/lib/csv.ts#L1)

**Executable contract**

- Behavioral cases cover formula, control-prefix, numeric, and quoting boundaries.
  [`check-project-workbench-regressions.mjs:42`](../../frontend/scripts/check-project-workbench-regressions.mjs#L42)

- Consumer assertion locks the workbench to the security serializer.
  [`check-project-workbench-regressions.mjs:138`](../../frontend/scripts/check-project-workbench-regressions.mjs#L138)
