import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import ts from 'typescript'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

registerHooks({
  resolve(specifier, context, nextResolve) {
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
    if (url.endsWith('.ts') || url.endsWith('.tsx')) {
      const result = ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: {
          jsx: ts.JsxEmit.ReactJSX,
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
        },
        fileName: fileURLToPath(url),
      })
      return { format: 'module', source: result.outputText, shortCircuit: true }
    }
    return nextLoad(url, context)
  },
})

const proposal = await import(pathToFileURL(path.join(frontendRoot, 'lib/workflow/proposal.ts')).href)
const demandDraft = await import(pathToFileURL(path.join(frontendRoot, 'lib/workflow/backend-demand-draft.ts')).href)
const toReactFlow = await import(pathToFileURL(path.join(frontendRoot, 'lib/workflow/to-react-flow.ts')).href)
const collectorTestRun = await import(pathToFileURL(path.join(frontendRoot, 'lib/workflow/collector-test-run.ts')).href)

function project(sources = [webSource('alpha', 'https://a.example')], execution = { concurrency: 2 }) {
  return {
    id: 'collector-project',
    name: 'Collector',
    profile: 'intelligence',
    version: 1,
    nodes: [{
      id: 'collector',
      kind: 'source',
      capability: 'fetch',
      params: { version: 1, sources, execution },
      ui: { catalogId: 'collection.source.web' },
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
}

function webSource(sourceId, url, extra = {}) {
  return { sourceId, kind: 'web', name: sourceId, enabled: true, url, fetchMode: 'auto', ...extra }
}

function collectorProposal(current, operations) {
  return {
    proposalId: 'proposal-1',
    nodeId: 'collector',
    baseRevision: proposal.getCollectorNodeRevision(current.nodes[0]),
    summary: 'Edit collector sources',
    operations,
  }
}

test('collector proposal applies atomically when its node revision matches', () => {
  const current = project()
  const input = collectorProposal(current, [{
    type: 'updateSource',
    sourceId: 'alpha',
    changes: { url: 'https://new.example' },
    expected: { url: { exists: true, value: 'https://a.example' } },
  }])
  const decision = proposal.acceptCollectorNodeProposal(current, input)
  assert.equal(decision.status, 'accepted')
  assert.equal(decision.changed, true)
  assert.equal(decision.project.nodes[0].params.sources[0].url, 'https://new.example')
  assert.equal(current.nodes[0].params.sources[0].url, 'https://a.example', 'input project is not mutated')
  assert.equal(decision.differences[0].status, 'change')
})

test('stale proposal safely rebases when unrelated collector state changed', () => {
  const base = project()
  const input = collectorProposal(base, [{
    type: 'updateSource',
    sourceId: 'alpha',
    changes: { url: 'https://new.example' },
    expected: { url: { exists: true, value: 'https://a.example' } },
  }])
  const manuallyEdited = project([webSource('alpha', 'https://a.example', { selector: 'article' })])
  const decision = proposal.acceptCollectorNodeProposal(manuallyEdited, input)
  assert.equal(decision.status, 'rebased')
  assert.equal(decision.project.nodes[0].params.sources[0].selector, 'article')
  assert.equal(decision.project.nodes[0].params.sources[0].url, 'https://new.example')
  assert.equal(decision.proposal.baseRevision, proposal.getCollectorNodeRevision(manuallyEdited.nodes[0]))
})

test('stale proposal conflicts instead of overwriting the same field', () => {
  const base = project()
  const input = collectorProposal(base, [{
    type: 'updateSource',
    sourceId: 'alpha',
    changes: { url: 'https://agent.example' },
    expected: { url: { exists: true, value: 'https://a.example' } },
  }])
  const manuallyEdited = project([webSource('alpha', 'https://human.example')])
  const decision = proposal.acceptCollectorNodeProposal(manuallyEdited, input)
  assert.equal(decision.status, 'conflict')
  assert.equal(decision.changed, false)
  assert.strictEqual(decision.project, manuallyEdited)
  assert.equal(decision.project.nodes[0].params.sources[0].url, 'https://human.example')
  assert.match(decision.conflicts[0], /changed since/)
})

test('later conflict in a multi-operation proposal leaves the project fully unchanged', () => {
  const current = project()
  const input = collectorProposal(current, [
    {
      type: 'updateSource',
      sourceId: 'alpha',
      changes: { url: 'https://would-have-changed.example' },
      expected: { url: { exists: true, value: 'https://a.example' } },
    },
    {
      type: 'updateSource',
      sourceId: 'missing',
      changes: { url: 'https://missing.example' },
      expected: { url: { exists: false } },
    },
  ])

  const decision = proposal.acceptCollectorNodeProposal(current, input)

  assert.equal(decision.status, 'conflict')
  assert.equal(decision.changed, false)
  assert.strictEqual(decision.project, current)
  assert.equal(current.nodes[0].params.sources[0].url, 'https://a.example')
  assert.equal(decision.project.nodes[0].params.sources[0].url, 'https://a.example')
  assert.equal(decision.differences[0].status, 'change')
  assert.equal(decision.differences[1].status, 'conflict')
})

test('accepted collector proposal is idempotent when replayed', () => {
  const current = project()
  const input = collectorProposal(current, [{
    type: 'addSource',
    source: webSource('beta', 'https://b.example'),
  }])
  const first = proposal.acceptCollectorNodeProposal(current, input)
  const replay = proposal.acceptCollectorNodeProposal(first.project, input)
  assert.equal(replay.status, 'rebased')
  assert.equal(replay.changed, false)
  assert.equal(replay.project.nodes[0].params.sources.length, 2)
})

test('reject leaves the project untouched and structured whitelist blocks executable or secret fields', () => {
  const current = project()
  const input = collectorProposal(current, [{
    type: 'setExecution',
    field: 'timeoutMs',
    value: 5000,
    expected: { exists: false },
  }])
  const rejected = proposal.rejectCollectorNodeProposal(current, input)
  assert.equal(rejected.status, 'rejected')
  assert.strictEqual(rejected.project, current)

  assert.throws(() => proposal.parseCollectorNodeProposal({
    ...input,
    operations: [{
      type: 'addSource',
      source: { sourceId: 'unsafe', kind: 'cli', adapterNodeId: 'registered', args: { rawCommand: 'rm -rf' } },
    }],
  }), /forbidden/)
  assert.throws(() => proposal.parseCollectorNodeProposal({
    ...input,
    operations: [{
      type: 'addSource',
      source: { sourceId: 'unsafe', kind: 'cli', adapterNodeId: 'registered', commandLine: 'echo nope' },
    }],
  }), /not editable|forbidden/)

  const wrongKind = collectorProposal(current, [{
    type: 'addSource',
    source: { sourceId: 'feed', kind: 'rss', name: 'feed', enabled: true, feedUrl: 'https://feed.example', itemLimit: 20 },
  }])
  const wrongKindDecision = proposal.acceptCollectorNodeProposal(current, wrongKind)
  assert.equal(wrongKindDecision.status, 'conflict')
  assert.match(wrongKindDecision.conflicts[0], /cannot accept/)
})

test('collector secret denylist normalizes API key and OAuth token variants', () => {
  const current = project()
  const unsafeKeys = ['x-api-key', 'X_API_KEY', 'access_token', 'refresh-token', 'client_secret']
  for (const key of unsafeKeys) {
    assert.throws(() => proposal.parseCollectorNodeProposal({
      ...collectorProposal(current, []),
      operations: [{
        type: 'addSource',
        source: webSource('unsafe', 'https://unsafe.example', { extraction: { [key]: 'plaintext' } }),
      }],
    }), /forbidden/, key)
  }
})

test('legacy Merge in1/in2 edges map onto the single logical in handle', () => {
  const current = project()
  current.nodes.push({
    id: 'merge',
    kind: 'flow',
    capability: 'merge',
    params: {},
    ui: { catalogId: 'flow.merge' },
  })
  current.edges.push({
    id: 'legacy-edge',
    source: 'collector',
    target: 'merge',
    sourcePort: 'out',
    targetPort: 'in2',
  })
  const projection = toReactFlow.workflowProjectToReactFlow(current)
  assert.equal(projection.edges[0].targetHandle, 'in')
  assert.equal(projection.edges[0].data.targetPort, 'in')
})

test('single-source test uses a temporary real workflow run and returns backend sourceResults', async () => {
  const current = project([
    webSource('alpha', 'https://a.example'),
    webSource('beta', 'https://b.example'),
  ])
  const requests = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, init = {}) => {
    requests.push({ url: String(url), init })
    if (String(url) === '/api/workflow/run') {
      return jsonResponse({
        success: true,
        data: {
          workflowId: 'temporary',
          runId: 'run-1',
          traceId: 'trace-1',
          valid: true,
          status: 'completed',
          startedAt: '2026-07-24T00:00:00Z',
          updatedAt: '2026-07-24T00:00:01Z',
          eventCount: 2,
          nodeStates: [],
          errors: [],
        },
      })
    }
    return jsonResponse({
      success: true,
      data: {
        projection: {
          workflowId: 'temporary',
          runId: 'run-1',
          traceId: 'trace-1',
          valid: true,
          status: 'completed',
          startedAt: '2026-07-24T00:00:00Z',
          updatedAt: '2026-07-24T00:00:01Z',
          eventCount: 2,
          nodeStates: [],
          errors: [],
        },
        checkpoint: {},
        filters: { nodeId: 'collector' },
        nextAfterSequence: 2,
        events: [{
          id: 'event-2',
          sequence: 2,
          workflowId: 'temporary',
          workflowRunId: 'run-1',
          traceId: 'trace-1',
          nodeId: 'collector',
          eventType: 'partial',
          createdAt: '2026-07-24T00:00:01Z',
          details: {
            items: [],
            sourceResults: [{
              sourceId: 'beta',
              status: 'completed',
              itemCount: 0,
              attempts: 1,
              startedAt: '2026-07-24T00:00:00Z',
              finishedAt: '2026-07-24T00:00:01Z',
            }],
          },
        }],
      },
    })
  }
  try {
    const output = await collectorTestRun.runCollectorSourceTest(
      current,
      'collector',
      current.nodes[0].params,
      [current.nodes[0].params.sources[1]],
    )
    assert.equal(output.sourceResults[0].sourceId, 'beta')
    assert.equal(requests.length, 2)
    const runBody = JSON.parse(requests[0].init.body)
    assert.equal(runBody.ephemeral, true)
    assert.equal(runBody.project.nodes.length, 1)
    assert.equal(runBody.project.edges.length, 0)
    assert.equal(runBody.project.nodes[0].params.sources.length, 1)
    assert.equal(runBody.project.nodes[0].params.sources[0].sourceId, 'beta')
    assert.equal(runBody.project.agentPermissions.canFetchNetwork, true)
    assert.match(requests[1].url, /nodeId=collector/)
  } finally {
    globalThis.fetch = originalFetch
  }
})

function jsonResponse(body) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

test('backend collector demand is converted to a node-scoped revision-bound proposal', async () => {
  const current = project()
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({
    success: true,
    data: {
      valid: true,
      errors: [],
      missing_capabilities: [],
      patch: {
        operations: [{
          op: 'update_parameters',
          nodeId: 'collector',
          params: {
            sources: [webSource('alpha', 'https://a.example', { selector: 'article' })],
            execution: { concurrency: 4 },
          },
        }],
      },
    },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  try {
    const drafted = await demandDraft.draftCollectorNodeDemand(current, 'collector', 'collect articles')
    assert.equal(drafted.nodeId, 'collector')
    assert.equal(drafted.baseRevision, proposal.getCollectorNodeRevision(current.nodes[0]))
    assert.deepStrictEqual(drafted.operations.map((operation) => operation.type), ['updateSource', 'setExecution'])
    const accepted = proposal.acceptCollectorNodeProposal(current, drafted)
    assert.equal(accepted.status, 'accepted')
    assert.equal(accepted.project.nodes[0].params.sources[0].selector, 'article')
    assert.equal(accepted.project.nodes[0].params.execution.concurrency, 4)
  } finally {
    globalThis.fetch = originalFetch
  }
})
