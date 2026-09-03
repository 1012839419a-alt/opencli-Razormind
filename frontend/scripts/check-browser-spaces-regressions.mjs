import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('Browser Spaces client exposes the complete lifecycle contract', async () => {
  const api = await read('lib/api/browser-spaces.ts')
  for (const operation of [
    'listBrowserSpaces',
    'createBrowserSpace',
    'getBrowserSpace',
    'submitBrowserSpaceTask',
    'cancelBrowserSpace',
    'closeBrowserSpace',
    'listBrowserSpaceEvents',
  ]) {
    assert.match(api, new RegExp(`export const ${operation}`))
  }
  assert.match(api, /after_sequence/)
  assert.match(api, /encodeURIComponent\(workspaceId\)/)
  assert.match(api, /encodeURIComponent\(spaceId\)/)
})

test('the operator panel is mounted on the existing browsers surface', async () => {
  const page = await read('app/(app)/browsers/page.tsx')
  const panel = await read('components/browsers/browser-spaces-panel.tsx')
  assert.match(page, /BrowserSpacesPanel/)
  assert.match(panel, /listBrowserSpaces/)
  assert.match(panel, /createBrowserSpace/)
  assert.match(panel, /submitBrowserSpaceTask/)
  assert.match(panel, /page\.metadata/)
})

test('task controls include explicit cancel and close confirmation', async () => {
  const panel = await read('components/browsers/browser-spaces-panel.tsx')
  assert.match(panel, /cancelBrowserSpace/)
  assert.match(panel, /closeBrowserSpace/)
  assert.match(panel, /确认取消/)
  assert.match(panel, /确认关闭/)
})

test('runtime conflict and isolation errors remain visible without fallback', async () => {
  const panel = await read('components/browsers/browser-spaces-panel.tsx')
  for (const code of ['browser_instance_in_use', 'space_task_in_progress', 'isolation_unavailable']) {
    assert.match(panel, new RegExp(code))
  }
  assert.match(panel, /无共享标签页回退/)
  assert.doesNotMatch(panel, /workers\/chrome-pool|https?:\/\/|remote-debugging-port|document\.cookie|authorization:/i)
})

test('space output is limited to opaque IDs, ordered events, and redacted result projections', async () => {
  const api = await read('lib/api/browser-spaces.ts')
  const panel = await read('components/browsers/browser-spaces-panel.tsx')
  assert.match(api, /BrowserSpaceEvent/)
  assert.match(panel, /event\.sequence/)
  assert.match(panel, /activeTask\.result/)
  assert.match(panel, /MAX_ARGS_BYTES/)
  assert.doesNotMatch(panel, /https?:\/\/|document\.cookie|authorization:/i)
})
