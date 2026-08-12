import { WORKFLOW_NODE_CATALOG, createWorkflowNodeFromCatalog } from './node-catalog'
import { parseWorkflowProject, type WorkflowProjectNode } from './schema'

export type GaojixingDoubaoWorkflowOptions = {
  sourceMode?: 'offline_fixture' | 'project_archive'
  fixtureId?: string
  feishuWebhookEnv?: string
}

const DEFAULT_FIXTURE_ID = 'gaojixing-doubao-offline-v1'
const DEFAULT_FEISHU_WEBHOOK_ENV = 'GAOJIXING_FEISHU_WEBHOOK_URL'

function catalog(id: string) {
  const item = WORKFLOW_NODE_CATALOG.find((candidate) => candidate.id === id)
  if (!item) throw new Error(`工作流节点未注册：${id}`)
  return item
}

function withParams(
  node: WorkflowProjectNode,
  params: Record<string, unknown>,
): WorkflowProjectNode {
  return { ...node, params: { ...node.params, ...params } }
}

/**
 * Build the Gaojixing workflow from two deep business capabilities.
 *
 * The canvas intentionally exposes only trigger → collection HDA →
 * certification HDA → delivery. Per-question evidence checks, phase gates,
 * recovery cases and final reconciliation stay inside the two backend
 * capabilities instead of becoming dozens of misleading canvas nodes.
 */
export function buildGaojixingDoubaoWorkflow(
  name: string,
  options: GaojixingDoubaoWorkflowOptions = {},
) {
  const requestedSourceMode = String(options.sourceMode ?? 'project_archive')
  if (requestedSourceMode !== 'offline_fixture' && requestedSourceMode !== 'project_archive') {
    throw new Error(
      `Source mode "${requestedSourceMode}" does not produce a certifiable batch; live_preflight is an independent read-only readiness check.`,
    )
  }
  const sourceMode = requestedSourceMode
  const fixtureId = options.fixtureId ?? DEFAULT_FIXTURE_ID
  const sharedParams = {
    sourceMode,
    ...(sourceMode === 'offline_fixture' ? { fixtureId } : {}),
    requirePhase1BeforePhase2: true,
    feishuWebhookEnv: options.feishuWebhookEnv ?? DEFAULT_FEISHU_WEBHOOK_ENV,
  }
  const runInputSchema = sourceMode === 'project_archive'
    ? {
        type: 'object',
        additionalProperties: false,
        required: ['questionBankPath', 'projectRoot'],
        properties: {
          questionBankPath: { type: 'string', minLength: 1, title: '本次题包路径' },
          projectRoot: { type: 'string', minLength: 1, title: '本次批次目录' },
        },
      }
    : {
        type: 'object',
        additionalProperties: false,
        required: [],
        properties: {},
      }

  const trigger = withParams(
    createWorkflowNodeFromCatalog(catalog('intelligence.schedule.cron'), 'trigger', { x: 80, y: 180 }),
    {
      interval: 'manual',
      timezone: 'Asia/Shanghai',
      mode: 'manual',
      inputSchema: runInputSchema,
    },
  )
  const collection = withParams(
    createWorkflowNodeFromCatalog(
      catalog('package.gaojixing.doubao-batch'),
      'gaojixing-doubao-batch',
      { x: 440, y: 180 },
    ),
    sharedParams,
  )
  const certification = withParams(
    createWorkflowNodeFromCatalog(
      catalog('package.gaojixing.batch-certification'),
      'gaojixing-batch-certification',
      { x: 840, y: 180 },
    ),
    sharedParams,
  )
  const delivery = withParams(
    createWorkflowNodeFromCatalog(catalog('intelligence.output.inbox'), 'delivery', { x: 1240, y: 180 }),
    { queue: 'gaojixing-doubao-certified', archive: true },
  )

  return parseWorkflowProject({
    id: `draft-${Date.now()}`,
    name,
    profile: 'intelligence',
    version: 1,
    nodes: [trigger, collection, certification, delivery],
    edges: [
      { id: 'trigger-collection', source: trigger.id, target: collection.id, sourcePort: 'tick', targetPort: 'in' },
      { id: 'collection-certification', source: collection.id, target: certification.id, sourcePort: 'out', targetPort: 'in' },
      { id: 'certification-delivery', source: certification.id, target: delivery.id, sourcePort: 'out', targetPort: 'in' },
    ],
    adapters: [],
    agentPermissions: {
      canFetchNetwork: false,
      canSendNotifications: true,
      canWriteInbox: true,
    },
  })
}
