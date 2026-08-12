import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import test from 'node:test'
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

const catalogSource = await readFile(new URL('../lib/workflow/node-catalog.ts', import.meta.url), 'utf8')
const workflowSource = await readFile(new URL('../lib/workflow/gaojixing-doubao-workflow.ts', import.meta.url), 'utf8')
const templateSource = await readFile(new URL('../lib/workflow/studio-templates.ts', import.meta.url), 'utf8')
const runProxySource = await readFile(new URL('../app/api/workflow/run/route.ts', import.meta.url), 'utf8')
const runPanelSource = await readFile(new URL('../components/flow/run-trace-panel.tsx', import.meta.url), 'utf8')

test('Gaojixing canvas uses two real deep capabilities instead of a bloated primitive graph', () => {
  assert.match(catalogSource, /id: "package\.gaojixing\.doubao-batch"/)
  assert.match(catalogSource, /"tool\.gaojixing\.doubao-batch\.run"/)
  assert.match(catalogSource, /"gaojixing_doubao_batch"/)
  assert.match(catalogSource, /id: "package\.gaojixing\.batch-certification"/)
  assert.match(catalogSource, /"tool\.gaojixing\.batch-certify"/)
  assert.match(catalogSource, /"gaojixing_batch_certify"/)

  assert.match(workflowSource, /nodes: \[trigger, collection, certification, delivery\]/)
  assert.match(workflowSource, /source: collection\.id, target: certification\.id/)
  assert.doesNotMatch(workflowSource, /captcha[-_ ]wait|human[-_ ]approval|design_only/i)
})

test('Gaojixing HDA internals match the backend single-tool materialization', async () => {
  const [{ WORKFLOW_NODE_CATALOG }, { buildGaojixingDoubaoWorkflow }] = await Promise.all([
    importTypeScript('lib/workflow/node-catalog.ts'),
    importTypeScript('lib/workflow/gaojixing-doubao-workflow.ts'),
  ])
  const project = buildGaojixingDoubaoWorkflow('Gaojixing regression')
  const expectedTools = new Map([
    ['package.gaojixing.doubao-batch', 'tool.gaojixing.doubao-batch.run'],
    ['package.gaojixing.batch-certification', 'tool.gaojixing.batch-certify'],
  ])

  for (const [catalogId, toolId] of expectedTools) {
    const catalogItem = WORKFLOW_NODE_CATALOG.find((candidate) => candidate.id === catalogId)
    assert.ok(catalogItem, `missing catalog item ${catalogId}`)
    assert.equal(catalogItem.topicCollapse?.nodeCount, 1)
    assert.equal(catalogItem.internals?.locked, true)
    assert.deepEqual(catalogItem.internals?.nodes.map((node) => node.id), ['tool'])
    assert.equal(catalogItem.internals?.nodes[0]?.ui.catalogId, 'external.tool.capability')
    assert.equal(catalogItem.internals?.nodes[0]?.params.toolCapability?.id, toolId)
    assert.deepEqual(catalogItem.internals?.edges, [])
    if (catalogId === 'package.gaojixing.doubao-batch') {
      assert.equal(catalogItem.params.feishuWebhookEnv, 'GAOJIXING_FEISHU_WEBHOOK_URL')
      assert.equal(
        catalogItem.internals?.nodes[0]?.params.toolParams?.feishuWebhookEnv,
        'GAOJIXING_FEISHU_WEBHOOK_URL',
      )
    }

    const workflowNode = project.nodes.find((node) => node.ui.catalogId === catalogId)
    assert.ok(workflowNode, `missing instantiated node ${catalogId}`)
    assert.equal(workflowNode.topicCollapse?.nodeCount, 1)
    assert.deepEqual(workflowNode.internals?.nodes.map((node) => node.id), ['tool'])
    assert.deepEqual(workflowNode.internals?.edges, [])
  }

  const unrelatedPackage = WORKFLOW_NODE_CATALOG.find(
    (candidate) => candidate.id === 'package.intelligence.situation-awareness',
  )
  assert.ok(unrelatedPackage)
  assert.equal(unrelatedPackage.topicCollapse?.nodeCount, 2)
  assert.deepEqual(unrelatedPackage.internals?.nodes.map((node) => node.id), ['tool', 'output'])
  assert.equal(unrelatedPackage.internals?.edges.length, 1)
})

test('Gaojixing workflow has exactly four nodes and a backend-recognizable manual trigger', async () => {
  const { buildGaojixingDoubaoWorkflow } = await importTypeScript(
    'lib/workflow/gaojixing-doubao-workflow.ts',
  )
  const project = buildGaojixingDoubaoWorkflow('Gaojixing manual run')

  assert.deepEqual(
    project.nodes.map((node) => ({ id: node.id, catalogId: node.ui.catalogId })),
    [
      { id: 'trigger', catalogId: 'intelligence.schedule.cron' },
      { id: 'gaojixing-doubao-batch', catalogId: 'package.gaojixing.doubao-batch' },
      { id: 'gaojixing-batch-certification', catalogId: 'package.gaojixing.batch-certification' },
      { id: 'delivery', catalogId: 'intelligence.output.inbox' },
    ],
  )
  const trigger = project.nodes[0]
  assert.equal(trigger.kind, 'schedule')
  assert.equal(trigger.params.interval, 'manual')
  assert.equal(trigger.params.timezone, 'Asia/Shanghai')
  assert.equal(trigger.params.mode, 'manual')
  assert.equal(
    project.nodes[1].params.feishuWebhookEnv,
    'GAOJIXING_FEISHU_WEBHOOK_URL',
  )
})

test('Gaojixing certification copy promises structural evidence checks, not visual or OCR review', async () => {
  const { WORKFLOW_NODE_CATALOG } = await importTypeScript('lib/workflow/node-catalog.ts')
  const collection = WORKFLOW_NODE_CATALOG.find(
    (candidate) => candidate.id === 'package.gaojixing.doubao-batch',
  )
  const certification = WORKFLOW_NODE_CATALOG.find(
    (candidate) => candidate.id === 'package.gaojixing.batch-certification',
  )

  assert.ok(collection)
  assert.match(collection.description, /live_preflight.*独立.*只读就绪检查/)
  assert.match(collection.description, /不产生批次结果.*不进入.*终审/)
  assert.match(collection.description, /通知权限.*feishuWebhookEnv.*同时满足/)
  assert.ok(certification)
  assert.equal(certification.label, '批次证据结构终审与交付')
  assert.match(certification.description, /证据结构终审/)
  assert.match(certification.description, /文件存在/)
  assert.match(certification.description, /引用一致性/)
  assert.match(certification.description, /不执行截图视觉或 OCR 内容判定/)
})

test('Gaojixing four-node template exposes only source modes that produce certifiable batches', async () => {
  const { buildGaojixingDoubaoWorkflow } = await importTypeScript(
    'lib/workflow/gaojixing-doubao-workflow.ts',
  )

  assert.match(templateSource, /id: 'gaojixing-doubao-evidence'/)
  assert.match(templateSource, /return buildGaojixingDoubaoWorkflow\(name\)/)
  assert.match(workflowSource, /sourceMode \?\? 'project_archive'/)
  assert.match(workflowSource, /sourceMode\?: 'offline_fixture' \| 'project_archive'/)
  assert.doesNotMatch(workflowSource, /sourceMode\?:[^\n]*live_preflight/)
  assert.match(workflowSource, /sourceMode === 'offline_fixture'/)
  assert.throws(
    () => buildGaojixingDoubaoWorkflow('Invalid preflight batch', { sourceMode: 'live_preflight' }),
    /live_preflight.*does not produce a certifiable batch/,
  )
  assert.match(workflowSource, /canFetchNetwork: false/)
  assert.match(workflowSource, /canSendNotifications: true/)
  assert.match(workflowSource, /questionBankPath/)
  assert.match(workflowSource, /feishuWebhookEnv/)
})

test('Gaojixing template requires a fresh question batch per run and never persists batch counts', async () => {
  const { buildGaojixingDoubaoWorkflow } = await importTypeScript(
    'lib/workflow/gaojixing-doubao-workflow.ts',
  )
  const project = buildGaojixingDoubaoWorkflow('Fresh questions every run')
  const trigger = project.nodes.find((node) => node.id === 'trigger')
  const collection = project.nodes.find((node) => node.id === 'gaojixing-doubao-batch')
  const certification = project.nodes.find((node) => node.id === 'gaojixing-batch-certification')

  assert.ok(trigger)
  assert.deepEqual(trigger.params.inputSchema, {
    type: 'object',
    additionalProperties: false,
    required: ['questionBankPath', 'projectRoot'],
    properties: {
      questionBankPath: { type: 'string', minLength: 1, title: '本次题包路径' },
      projectRoot: { type: 'string', minLength: 1, title: '本次批次目录' },
    },
  })
  assert.ok(collection)
  assert.ok(certification)
  assert.equal(collection.params.sourceMode, 'project_archive')
  assert.equal(certification.params.sourceMode, 'project_archive')
  for (const node of [collection, certification]) {
    assert.equal('questionBankPath' in node.params, false)
    assert.equal('projectRoot' in node.params, false)
    assert.equal('phase1Expected' in node.params, false)
    assert.equal('phase2Expected' in node.params, false)
  }

  assert.doesNotMatch(workflowSource, /phase1Expected|phase2Expected/)
  assert.doesNotMatch(workflowSource, /questionBankPath\?:|projectRoot\?:/)
  assert.match(catalogSource, /每次运行.*新题包/)
  const templateCopy = templateSource.match(/id: 'gaojixing-doubao-evidence'[^\n]+/)?.[0] ?? ''
  assert.match(templateCopy, /每次运行.*新题包/)
  assert.doesNotMatch(templateCopy, /446|32|默认离线夹具/)
})

test('Workflow Run forwards the fresh batch input and recognizes the Gaojixing trigger as manual', async () => {
  const [{ buildGaojixingDoubaoWorkflow }, { startWorkflowRun }] = await Promise.all([
    importTypeScript('lib/workflow/gaojixing-doubao-workflow.ts'),
    importTypeScript('lib/workflow/backend-runs.ts'),
  ])
  const project = buildGaojixingDoubaoWorkflow('Fresh run input')
  const input = {
    payload: {
      questionBankPath: 'D:/batches/run-2026-08-12/questions.json',
      projectRoot: 'D:/batches/run-2026-08-12',
    },
    source: 'operator',
  }
  const originalFetch = globalThis.fetch
  let requestBody
  globalThis.fetch = async (_url, init) => {
    requestBody = JSON.parse(String(init?.body))
    return Response.json({ success: true, data: { runId: 'run-fresh-batch' } })
  }
  try {
    await startWorkflowRun(project, { input })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(requestBody.input, input)
  assert.deepEqual(requestBody.trigger, { kind: 'manual', triggerNodeId: 'trigger' })
  assert.match(runProxySource, /body\?\.input[\s\S]*\{ input: body\.input \}/)
})

test('Studio Run input follows the trigger schema and refuses an empty Gaojixing batch', async () => {
  const [{ buildGaojixingDoubaoWorkflow }, runClient] = await Promise.all([
    importTypeScript('lib/workflow/gaojixing-doubao-workflow.ts'),
    importTypeScript('lib/workflow/backend-runs.ts'),
  ])
  const project = buildGaojixingDoubaoWorkflow('Studio fresh batch')

  assert.deepEqual(runClient.buildWorkflowRunInputTemplate(project), {
    questionBankPath: '',
    projectRoot: '',
  })
  assert.throws(
    () => runClient.parseWorkflowRunInput(project, '{}'),
    /questionBankPath.*required/,
  )
  assert.deepEqual(
    runClient.parseWorkflowRunInput(
      project,
      JSON.stringify({ questionBankPath: 'D:/new/questions.json', projectRoot: 'D:/new' }),
    ),
    {
      payload: { questionBankPath: 'D:/new/questions.json', projectRoot: 'D:/new' },
      source: 'operator',
    },
  )
  const fixtureProject = buildGaojixingDoubaoWorkflow('Offline fixture', {
    sourceMode: 'offline_fixture',
  })
  assert.deepEqual(runClient.buildWorkflowRunInputTemplate(fixtureProject), {})
  assert.deepEqual(runClient.parseWorkflowRunInput(fixtureProject, '{}'), {
    payload: {},
    source: 'operator',
  })
  assert.match(runPanelSource, /parseWorkflowRunInput\(workflowProject, runInputText\)/)
  assert.match(runPanelSource, /startWorkflowRun\(workflowProject, \{ authorization, sourceOutputs, input \}\)/)
  assert.match(runPanelSource, /aria-label="本次运行输入 JSON"/)
})
