import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'dagre') return { url: 'dagre:test-stub', shortCircuit: true }
    const candidates = []
    if (specifier.startsWith('@/')) {
      candidates.push(path.join(frontendRoot, specifier.slice(2)))
    } else if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
      candidates.push(path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier))
    }
    for (const candidate of candidates) {
      for (const resolvedPath of [candidate, `${candidate}.ts`, `${candidate}.tsx`]) {
        if (existsSync(resolvedPath)) {
          return { url: pathToFileURL(resolvedPath).href, shortCircuit: true }
        }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url === 'dagre:test-stub') {
      return {
        format: 'module',
        source: 'export default { graphlib: { Graph: class Graph {} }, layout() {} }',
        shortCircuit: true,
      }
    }
    if (url.endsWith('.ts') || url.endsWith('.tsx')) {
      const source = stripTypeScriptTypes(readFileSync(fileURLToPath(url), 'utf8'), {
        mode: 'strip',
        sourceUrl: url,
      })
      return { format: 'module', source, shortCircuit: true }
    }
    if (url.endsWith('.json')) {
      const json = readFileSync(fileURLToPath(url), 'utf8')
      return { format: 'module', source: `export default ${json}`, shortCircuit: true }
    }
    return nextLoad(url, context)
  },
})

const importTypeScript = (relativePath) => import(pathToFileURL(path.join(frontendRoot, relativePath)).href)

test('loading runtime capability projections does not dirty the persisted workflow draft', async () => {
  const [{ useFlowStore }, { workflowDraftFingerprint }, { parseWorkflowProject }] = await Promise.all([
    importTypeScript('lib/flow/store.ts'),
    importTypeScript('lib/workflow/draft-persistence.ts'),
    importTypeScript('lib/workflow/schema.ts'),
  ])
  const project = {
    id: 'capability-projection-persistence',
    name: 'Capability projection persistence',
    profile: 'intelligence',
    version: 1,
    nodes: [{
      id: 'normalize',
      kind: 'agent',
      capability: 'normalize',
      params: {},
      ui: {
        catalogId: 'intelligence.processing.normalize',
        label: 'Normalize',
        position: { x: 0, y: 0 },
      },
    }],
    edges: [],
    settings: { timezone: 'Asia/Shanghai', deterministicSimulation: true, maxItemsPerRun: 20 },
    adapters: [],
    agentPermissions: {
      canFetchNetwork: false,
      canSendNotifications: false,
      canWriteInbox: true,
      allowedDomains: [],
    },
  }
  const contract = {
    schemaVersion: 1,
    bindingId: 'normalize',
    status: 'executable',
    inputShape: { ports: [{ name: 'in', type: 'items[]' }], params: [] },
    outputShape: { ports: [{ name: 'out', type: 'recordCandidate[]' }], artifacts: [] },
    permissionGate: { required: [] },
    configGate: { required: [] },
    eventShape: { events: [] },
    fixtureCoverage: { cases: [] },
    certification: { realNodeIoContract: true, realWebhookDelivery: false },
    canvas: { exposeResourceInternals: false },
  }

  useFlowStore.getState().importWorkflowProject(parseWorkflowProject(project))
  const before = workflowDraftFingerprint(useFlowStore.getState().workflowProject)
  useFlowStore.getState().applyWorkflowCapabilities({
    version: 'test',
    catalog: [{
      id: 'intelligence.processing.normalize',
      label: 'Normalize',
      surface: 'catalog',
      status: 'runnable',
      backendAvailable: true,
      kind: 'agent',
      capability: 'normalize',
      reason: null,
      missing: [],
      tags: ['test'],
      source: 'test.runtime',
      manifest: { contract },
    }],
    primitives: [],
    channels: [],
    notifiers: [],
    triggers: [],
    resources: [],
  })
  const after = workflowDraftFingerprint(useFlowStore.getState().workflowProject)

  assert.equal(after, before, 'runtime-only capability hydration must not schedule an autosave')
})

test('runtime capabilities are removed recursively without deleting authored contracts or parameter edits', async () => {
  const { persistableWorkflowProject, workflowDraftFingerprint } = await importTypeScript(
    'lib/workflow/draft-persistence.ts',
  )
  const runtimeCapability = { id: 'runtime.child', status: 'runnable' }
  const runtimeContract = { schemaVersion: 1, bindingId: 'runtime.child', status: 'executable' }
  const project = {
    id: 'nested-runtime-projection',
    name: 'Nested runtime projection',
    profile: 'intelligence',
    version: 1,
    nodes: [{
      id: 'package',
      kind: 'agent',
      capability: 'normalize',
      params: { authored: 'keep-me' },
      ui: { label: 'Package', position: { x: 0, y: 0 }, runtimeCapability, runtimeContract },
      internals: {
        locked: true,
        nodes: [{
          id: 'child',
          kind: 'agent',
          capability: 'normalize',
          params: {},
          ui: { label: 'Child', position: { x: 0, y: 0 }, runtimeCapability, runtimeContract },
        }],
        edges: [],
      },
    }],
    edges: [],
    settings: { timezone: 'Asia/Shanghai', deterministicSimulation: true, maxItemsPerRun: 20 },
    adapters: [],
    agentPermissions: {
      canFetchNetwork: false,
      canSendNotifications: false,
      canWriteInbox: true,
      canMutateExternalSites: false,
      allowedDomains: [],
    },
  }

  const persisted = persistableWorkflowProject(project)
  assert.equal(persisted.nodes[0].ui.runtimeCapability, undefined)
  assert.equal(persisted.nodes[0].ui.runtimeContract, runtimeContract)
  assert.equal(persisted.nodes[0].internals.nodes[0].ui.runtimeCapability, undefined)
  assert.equal(persisted.nodes[0].internals.nodes[0].ui.runtimeContract, runtimeContract)
  assert.equal(project.nodes[0].ui.runtimeContract, runtimeContract, 'persistence projection must not mutate editor state')

  const edited = {
    ...project,
    nodes: [{ ...project.nodes[0], params: { authored: 'changed-by-operator' } }],
  }
  assert.notEqual(
    workflowDraftFingerprint(edited),
    workflowDraftFingerprint(project),
    'authored parameter changes must still schedule an autosave',
  )
})

test('workflow switches isolate save queues and discard stale validation results', () => {
  const source = readFileSync(
    path.join(frontendRoot, 'components/flow/workflow-editor-session.tsx'),
    'utf8',
  )

  assert.match(source, /saveSession\.current \+= 1/)
  assert.ok(
    source.indexOf('saveSession.current += 1') < source.indexOf('if (primaryWorkflowPending) return'),
    'target changes must freeze autosave before waiting for the project primary workflow',
  )
  assert.match(source, /activeQueue\.target\.workspaceId/)
  assert.match(source, /saveSession\.current === activeQueue\.session/)
  assert.match(source, /workflowDraftFingerprint\(useFlowStore\.getState\(\)\.workflowProject\)/)
  assert.match(source, /saveSession\.current !== validationSession[\s\S]*?\) return/)
  assert.match(source, /saveSession\.current !== publishSession[\s\S]*?\) return/)
})
