import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const root = new URL('../', import.meta.url)

async function source(path) {
  return readFile(new URL(path, root), 'utf8')
}

test('CanvasHostBridge exposes the platform-owned authoring contract', async () => {
  const bridge = await source('features/image-studio/canvas-host-bridge.ts')

  for (const operation of [
    'loadDocument',
    'saveDocument',
    'createSnapshot',
    'listAssets',
    'importAsset',
    'getModelCatalog',
    'enqueueGeneration',
    'cancelGeneration',
    'getJobStatus',
    'subscribeJobEvents',
  ]) {
    assert.match(bridge, new RegExp(`\\b${operation}\\b`))
  }
  assert.match(bridge, /expectedRevision/)
})

test('browser bridge only targets OpenCLI platform routes', async () => {
  const bridge = await source('features/image-studio/platform-canvas-host-bridge.ts')

  assert.match(bridge, /\/image-studio/)
  assert.doesNotMatch(bridge, /invokeai|enqueue_batch|socket\.io|Authorization:\s*['\"]Bearer/i)
  assert.doesNotMatch(bridge, /localhost:\d+|127\.0\.0\.1:\d+/)
})

test('Image Studio is dynamically loaded as a client-only full-screen editor', async () => {
  const page = await source('app/(app)/studio/workflow/image/page.tsx')
  const host = await source('features/image-studio/image-studio-host.tsx')

  assert.match(page, /dynamic\s*\(/)
  assert.match(page, /ssr:\s*false/)
  assert.match(host, /Canvas/)
  assert.match(host, /图库/)
  assert.match(host, /生成图/)
  assert.match(host, /模型/)
  assert.match(host, /isPlatformAdmin/)
})

test('Image Studio owns and cleans up keyboard and job subscriptions', async () => {
  const host = await source('features/image-studio/image-studio-host.tsx')
  const provider = await source('features/image-studio/image-studio-provider.tsx')

  assert.match(host, /addEventListener\(['\"]keydown['\"]/)
  assert.match(host, /removeEventListener\(['\"]keydown['\"]/)
  assert.match(provider, /subscribeJobEvents/)
  assert.match(provider, /unsubscribe/)
})

test('first entry creates a valid document and returns its id to the workflow node', async () => {
  const bridge = await source('features/image-studio/platform-canvas-host-bridge.ts')
  const page = await source('app/(app)/studio/workflow/image/page.tsx')

  assert.match(bridge, /document:\s*\{\s*\.\.\.EMPTY_CANVAS_RECIPE/)
  assert.match(bridge, /onDocumentResolved\?\./)
  assert.match(page, /imageNode/)
  assert.match(page, /imageDocument/)
})

test('asset nodes can open gallery picker and return stable platform asset ids', async () => {
  const page = await source('app/(app)/studio/workflow/image/page.tsx')
  const host = await source('features/image-studio/image-studio-host.tsx')

  assert.match(page, /mode.*asset-picker/)
  assert.match(page, /imageAssets/)
  assert.match(host, /selectedAssetIds/)
})

test('asset pixels use authenticated object URLs without persisting browser URLs in Canvas JSON', async () => {
  const bridge = await source('features/image-studio/platform-canvas-host-bridge.ts')
  const host = await source('features/image-studio/image-studio-host.tsx')
  const provider = await source('features/image-studio/image-studio-provider.tsx')

  assert.match(bridge, /URL\.createObjectURL/)
  assert.match(bridge, /URL\.revokeObjectURL/)
  assert.doesNotMatch(host, /contentUrl:\s*asset\.contentUrl/)
  assert.match(provider, /bridge\.dispose\?\./)
})

test('job events fall back to REST reconciliation and treat blocked as terminal', async () => {
  const bridge = await source('features/image-studio/platform-canvas-host-bridge.ts')
  const provider = await source('features/image-studio/image-studio-provider.tsx')

  assert.match(bridge, /pollJobUntilTerminal/)
  assert.match(bridge, /getJobStatus/)
  assert.match(provider, /'blocked'/)
})

test('Canvas preview uses the immutable snapshot id as its bounded run identity', async () => {
  const bridge = await source('features/image-studio/platform-canvas-host-bridge.ts')

  assert.match(bridge, /runId:\s*input\.snapshotId/)
  assert.match(bridge, /mode:\s*['"]preview['"]/)
  assert.doesNotMatch(bridge, /canvas-preview-/)
})
