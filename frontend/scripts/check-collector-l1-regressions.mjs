import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

registerHooks({
  resolve(specifier, context, nextResolve) {
    const candidates = []
    if (specifier.startsWith('@/')) candidates.push(path.join(frontendRoot, specifier.slice(2)))
    else if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
      candidates.push(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier))
    }
    for (const candidate of candidates) {
      for (const resolvedPath of [candidate, `${candidate}.ts`, `${candidate}.tsx`]) {
        if (existsSync(resolvedPath)) return { url: pathToFileURL(resolvedPath).href, shortCircuit: true }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.ts') || url.endsWith('.tsx')) {
      return {
        format: 'module',
        source: stripTypeScriptTypes(readFileSync(fileURLToPath(url), 'utf8'), {
          mode: 'strip',
          sourceUrl: url,
        }),
        shortCircuit: true,
      }
    }
    return nextLoad(url, context)
  },
})

const importTypeScript = (relativePath) => import(pathToFileURL(path.join(frontendRoot, relativePath)).href)
const readSource = (relativePath) => readFile(path.join(frontendRoot, relativePath), 'utf8')

if (process.argv.includes('--print-catalog-defaults')) {
  const catalog = await importTypeScript('lib/workflow/node-catalog.ts')
  const defaults = catalog.COLLECTOR_NODE_CATALOG_IDS.map((catalogId) => {
    const item = catalog.WORKFLOW_NODE_CATALOG.find((candidate) => candidate.id === catalogId)
    assert.ok(item, `missing ${catalogId}`)
    return {
      id: `${catalogId.replaceAll('.', '-')}-default`,
      kind: item.kind,
      capability: item.capability,
      params: item.params,
      ui: { catalogId: item.id },
    }
  })
  console.log(JSON.stringify(defaults))
  process.exit(0)
}

test('catalog registers the four L1 collector nodes with type-safe source defaults', async () => {
  const catalog = await importTypeScript('lib/workflow/node-catalog.ts')
  const expected = new Map([
    ['collection.source.web', '网页采集'],
    ['collection.source.api', 'API 采集'],
    ['collection.source.rss', 'RSS 采集'],
    ['collection.source.cli', 'CLI 采集'],
  ])
  for (const [id, label] of expected) {
    const item = catalog.WORKFLOW_NODE_CATALOG.find((candidate) => candidate.id === id)
    assert.ok(item, `missing ${id}`)
    assert.equal(item.label, label)
    assert.equal(item.category, 'source')
    assert.equal(item.params.version, 1)
    assert.ok(catalog.isCollectorNodeParams(item.params, id.slice('collection.source.'.length)))
  }
  const web = catalog.createCollectorSource('web', 'web-default')
  const rss = catalog.createCollectorSource('rss', 'rss-default')
  assert.equal(web.fetchMode, 'auto')
  assert.equal(rss.itemLimit, 20)
  assert.equal('limit' in rss, false)
})

test('feature flag hides collector creation entries without invalidating saved collector nodes', async () => {
  const previous = process.env.NEXT_PUBLIC_COLLECTION_L1_NODES
  process.env.NEXT_PUBLIC_COLLECTION_L1_NODES = 'false'
  try {
    const [catalog, schema] = await Promise.all([
      importTypeScript('lib/workflow/node-catalog.ts'),
      importTypeScript('lib/workflow/schema.ts'),
    ])
    const visibleIds = catalog.getWorkflowNodeCatalog('intelligence').map((item) => item.id)
    assert.deepEqual(
      visibleIds.filter((id) => catalog.COLLECTOR_NODE_CATALOG_IDS.includes(id)),
      [],
    )

    const savedItem = catalog.WORKFLOW_NODE_CATALOG.find((item) => item.id === 'collection.source.web')
    const savedNode = catalog.createWorkflowNodeFromCatalog(savedItem, 'saved-web', { x: 0, y: 0 })
    const parsed = schema.parseWorkflowProject({
      id: 'saved-collector-project',
      name: 'Saved collector project',
      profile: 'intelligence',
      version: 1,
      nodes: [savedNode],
      edges: [],
      settings: { timezone: 'Asia/Shanghai', deterministicSimulation: true, maxItemsPerRun: 20 },
      adapters: [],
      agentPermissions: {
        canFetchNetwork: false,
        canSendNotifications: false,
        canWriteInbox: true,
        allowedDomains: [],
      },
    })
    assert.equal(parsed.nodes[0].ui.catalogId, 'collection.source.web')
  } finally {
    if (previous === undefined) delete process.env.NEXT_PUBLIC_COLLECTION_L1_NODES
    else process.env.NEXT_PUBLIC_COLLECTION_L1_NODES = previous
  }
})

test('collector contracts reject cross-kind sources and free CLI command or secret fields', async () => {
  const contracts = await importTypeScript('lib/workflow/node-contracts.ts')
  const base = {
    id: 'collector',
    kind: 'source',
    capability: 'fetch',
    ui: { catalogId: 'collection.source.cli' },
  }
  const valid = {
    ...base,
    params: {
      version: 1,
      execution: {},
      sources: [{ sourceId: 'cli-1', kind: 'cli', name: 'Search', enabled: true, adapterNodeId: 'opencli.adapter.site.search', args: { query: 'AI' } }],
    },
  }
  assert.deepEqual(contracts.validateNodeContract(valid), [])
  const invalid = {
    ...valid,
    params: {
      ...valid.params,
      sources: [{ sourceId: 'cli-1', kind: 'web', name: 'Unsafe', enabled: true, adapterNodeId: 'x', args: { rawCommand: 'rm -rf /', authorization: 'secret' } }],
    },
  }
  const findings = contracts.validateNodeContract(invalid)
  assert.ok(findings.some((finding) => finding.summary.includes('kind "cli"')))
  assert.ok(findings.some((finding) => finding.summary.includes('forbidden')))
})

test('Merge exposes one variadic logical input and resolves legacy in1/in2 edges', async () => {
  const [catalog, contracts] = await Promise.all([
    importTypeScript('lib/workflow/node-catalog.ts'),
    importTypeScript('lib/workflow/node-contracts.ts'),
  ])
  const sourceItem = catalog.WORKFLOW_NODE_CATALOG.find((item) => item.id === 'intelligence.processing.normalize')
  const mergeItem = catalog.WORKFLOW_NODE_CATALOG.find((item) => item.id === 'intelligence.flow.merge')
  const source = catalog.createWorkflowNodeFromCatalog(sourceItem, 'source', { x: 0, y: 0 })
  const merge = catalog.createWorkflowNodeFromCatalog(mergeItem, 'merge', { x: 300, y: 0 })
  const contract = contracts.getNodeContract(merge)
  const inputs = contract.ports.filter((port) => port.direction === 'input')
  assert.equal(inputs.length, 1)
  assert.equal(inputs[0].id, 'in')
  assert.equal(inputs[0].cardinality, 'many')
  assert.equal(inputs[0].minConnections, 1)
  const project = { id: 'p', name: 'P', profile: 'intelligence', version: 1, adapters: [], nodes: [source, merge], edges: [{ id: 'e', source: 'source', target: 'merge', targetPort: 'in2' }] }
  assert.equal(contracts.resolveEdgeContract(project, project.edges[0]).targetPort.id, 'in')
})

test('Inspector bounds collector preview and exposes ordered source controls without free Shell inputs', async () => {
  const inspector = await readSource('components/flow/inspector.tsx')
  assert.match(inspector, /output\.items\.slice\(0,\s*50\)/)
  assert.match(inspector, /publishedAt.*fetchedAt/)
  assert.match(inspector, /上移来源/)
  assert.match(inspector, /下移来源/)
  assert.match(inspector, /测试全部/)
  assert.match(inspector, /重试失败项/)
  assert.match(inspector, /已注册 adapterNodeId/)
  assert.doesNotMatch(inspector, /label="(?:Shell|commandLine|scriptText|rawCommand)"/i)
})
