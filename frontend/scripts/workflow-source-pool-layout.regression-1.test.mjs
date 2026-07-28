// Regression: ISSUE-001 — multi-source L2 fit view made 33 source nodes unreadable
// Found by /qa on 2026-07-29
// Report: .gstack/qa-reports/qa-report-127-0-0-1-2026-07-29-2.md

import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const storeSource = await readFile(new URL('../lib/flow/store.ts', import.meta.url), 'utf8')
const menuActionsSource = await readFile(
  new URL('../components/flow/workflow-node-menu-actions.ts', import.meta.url),
  'utf8',
)

test('multi-source networks use a compact grouped grid before fitView', () => {
  assert.match(storeSource, /function layoutOpenCLISourcePool\(/)
  assert.match(storeSource, /Math\.min\(4, Math\.max\(2, Math\.ceil\(Math\.sqrt\(sources\.length\)\)\)\)/)
  assert.match(storeSource, /if \(previousGroup && group !== previousGroup\) slot = Math\.ceil\(slot \/ columns\) \* columns/)
  assert.match(
    storeSource,
    /sourcePoolPositions\.get\(normalizedNode\.id\) \?\? readInternalPosition\(normalizedNode, index\)/,
  )
  assert.match(menuActionsSource, /count > 20 \? useFlowStore\.getState\(\)\.nodes\.slice\(0, 12\)/)
  assert.match(menuActionsSource, /minZoom: focusNodes \? 0\.55 : undefined/)
})
