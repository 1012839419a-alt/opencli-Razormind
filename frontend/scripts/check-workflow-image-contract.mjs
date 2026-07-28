import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const readSource = (relativePath) => readFile(path.join(frontendRoot, relativePath), 'utf8')

test('workflow schema exposes the first-party media generation contract', async () => {
  const schema = await readSource('lib/workflow/schema.ts')

  assert.match(schema, /workflowNodeKindSchema[\s\S]*["']media["']/)
  assert.match(schema, /workflowCapabilitySchema[\s\S]*["']generate["']/)
})

test('catalog separates image generation recipes from pinned image assets', async () => {
  const catalog = await readSource('lib/workflow/node-catalog.ts')

  assert.match(catalog, /IMAGE_GENERATION_CATALOG_ID\s*=\s*["']media\.image-generation["']/)
  assert.match(catalog, /IMAGE_ASSET_CATALOG_ID\s*=\s*["']media\.image-asset["']/)
  assert.match(catalog, /id:\s*IMAGE_GENERATION_CATALOG_ID[\s\S]*kind:\s*["']media["'][\s\S]*capability:\s*["']generate["']/)
  assert.match(catalog, /id:\s*IMAGE_ASSET_CATALOG_ID[\s\S]*kind:\s*["']media["'][\s\S]*capability:\s*["']fetch["']/)
  assert.match(catalog, /params:\s*\{\s*canvasDocumentId:\s*["']["']\s*\}/)
  assert.match(catalog, /params:\s*\{\s*assetIds:\s*\[\]\s*\}/)
  assert.doesNotMatch(catalog, /params:\s*\{[^}]*canvas(?:Json|State|Document)\s*:/i)
})

test('media node port contracts only expose stable OpenCLI asset references', async () => {
  const contracts = await readSource('lib/workflow/node-contracts.ts')

  assert.match(contracts, /["']media\.image-generation["']:\s*contract\(/)
  assert.match(contracts, /port\(["']prompt["'],\s*["']input["'],\s*["']text["']/)
  assert.match(contracts, /port\(["']assets["'],\s*["']output["'],\s*["']mediaAsset\[\]["']/)
  assert.match(contracts, /port\(["']generation["'],\s*["']output["'],\s*["']mediaGenerationResult["']/)
  assert.match(contracts, /["']media\.image-asset["']:\s*contract\([\s\S]*port\(["']assets["'],\s*["']output["'],\s*["']mediaAsset\[\]["']/)
  assert.match(contracts, /Invoke temporary URL/i)
})

test('generation node opens the full-screen first-party image studio with scoped ids', async () => {
  const [renderer, session] = await Promise.all([
    readSource('components/flow/nodes/workflow-node.tsx'),
    readSource('components/flow/workflow-editor-session.tsx'),
  ])

  assert.match(renderer, /\/studio\/workflow\/image/)
  for (const parameter of ['workspace', 'project', 'workflow', 'node', 'document']) {
    assert.match(renderer, new RegExp(`searchParams\\.set\\(["']${parameter}["']`))
  }
  assert.match(renderer, /runtimeRunState\?\.status\s*===\s*["']waiting["']/)
  assert.match(renderer, /snapshotId/)
  assert.match(renderer, /modelFingerprint/)
  assert.match(renderer, /recentAssetIds/)
  assert.match(renderer, /searchParams\.set\(["']mode["'],\s*["']gallery["']\)/)
  assert.match(renderer, /Select Workspace Assets/)
  assert.match(session, /params\.get\(["']imageNode["']\)/)
  assert.match(session, /params\.get\(["']imageDocument["']\)/)
  assert.match(session, /params\.get\(["']imageAssets["']\)/)
  assert.match(session, /updateWorkflowNodeParams\([^,]+,\s*\{\s*canvasDocumentId:/)
  assert.match(session, /updateWorkflowNodeParams\([^,]+,\s*\{\s*assetIds:/)
  assert.match(session, /searchParams\.delete\(["']imageNode["']\)/)
  assert.match(session, /searchParams\.delete\(["']imageDocument["']\)/)
  assert.match(session, /searchParams\.delete\(["']imageAssets["']\)/)
})
