import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const page = await readFile(new URL('../app/(app)/sources/page.tsx', import.meta.url), 'utf8')
const endpoints = await readFile(new URL('../lib/api/endpoints.ts', import.meta.url), 'utf8')

test('sources page uses workspace Source and project SourceBinding APIs', () => {
  assert.match(endpoints, /\/governance\/workspaces/)
  assert.match(page, /useGovernedWorkspaces\(\)/)
  assert.match(page, /useGovernedWorkspaceProjects\(workspaceId\)/)
  assert.match(endpoints, /\/workspaces\/\$\{workspaceId\}\/sources/)
  assert.match(endpoints, /\/workspaces\/\$\{workspaceId\}\/projects\/\$\{projectId\}\/source-bindings/)
  assert.match(page, /source_revision_number: source\.current_revision_number/)
  assert.doesNotMatch(page, /href=\{`\/sources\/\$\{source\.id\}`\}/)
})
