import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('provider catalog mounts reusable Feishu connection management', () => {
  const page = read('app/(app)/providers/catalog/page.tsx')
  const panel = read('components/providers/feishu-bitable-connection-panel.tsx')
  assert.match(page, /FeishuBitableConnectionPanel/)
  assert.match(panel, /type="password"/)
  assert.match(panel, /App Secret 只写入本机加密存储/)
  assert.doesNotMatch(panel, /app_secret_preview/)
})

test('workflow catalog and Inspector expose a secret-free Feishu sink', () => {
  const catalog = read('lib/workflow/node-catalog.ts')
  const inspector = read('components/flow/inspector.tsx')
  const editor = read('components/flow/feishu-bitable-target-editor.tsx')
  assert.match(catalog, /intelligence\.sink\.feishu-bitable/)
  assert.match(catalog, /recordId: "Record ID"/)
  assert.match(inspector, /FeishuBitableTargetEditor/)
  assert.match(editor, /connectionId/)
  assert.match(editor, /evidenceDigest/)
  assert.doesNotMatch(editor, /appSecret|app_secret/)
})

test('frontend API contracts keep credentials write-only', () => {
  const types = read('lib/api/types.ts')
  const endpoints = read('lib/api/endpoints.ts')
  assert.match(types, /app_secret\?: string/)
  assert.match(types, /has_app_secret: boolean/)
  assert.doesNotMatch(types, /app_secret: string\n/)
  assert.match(endpoints, /\/delivery-connections/)
})
