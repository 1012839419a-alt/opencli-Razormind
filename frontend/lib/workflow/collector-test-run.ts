import type {
  CollectorNodeParams,
  CollectorOutputV1,
  CollectorSourceDefinition,
} from "./node-catalog"
import { queryWorkflowRunTrace, startWorkflowRun } from "./backend-runs"
import type { WorkflowProject, WorkflowProjectNode } from "./schema"

export async function runCollectorSourceTest(
  project: WorkflowProject,
  nodeId: string,
  params: CollectorNodeParams,
  sources: CollectorSourceDefinition[],
  options: { authorization?: string | null } = {},
): Promise<CollectorOutputV1> {
  const node = findCollectorProjectNode(project.nodes, nodeId)
  if (!node) throw new Error(`Collector test target "${nodeId}" does not exist`)
  const testProject: WorkflowProject = {
    ...project,
    id: `${project.id}-collector-test-${Date.now()}`,
    name: `${project.name} collector test`,
    nodes: [{
      ...node,
      params: { ...params, sources: structuredClone(sources) },
      internals: undefined,
    }],
    edges: [],
    agentPermissions: { ...project.agentPermissions, canFetchNetwork: true },
  }
  const run = await startWorkflowRun(testProject, {
    authorization: options.authorization,
    ephemeral: true,
    runId: `collector-test-${crypto.randomUUID()}`,
    traceId: `collector-test-${crypto.randomUUID()}`,
  })
  const trace = await queryWorkflowRunTrace(run.runId, {
    authorization: options.authorization,
    nodeId,
    limit: 100,
  })
  for (const event of [...trace.events].reverse()) {
    const output = readCollectorOutput(event.details) ?? readCollectorOutput(event.blockReason?.details)
    if (output) return output
  }
  const nodeState = trace.projection.nodeStates.find((state) => state.nodeId === nodeId)
  throw new Error(
    nodeState?.blockReasons[0]?.message ??
      trace.projection.errors[0]?.message ??
      "Collector run returned no sourceResults",
  )
}

function findCollectorProjectNode(nodes: WorkflowProjectNode[], nodeId: string): WorkflowProjectNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node
    const nestedNodes = (node.internals?.nodes ?? []).filter(
      (candidate): candidate is WorkflowProjectNode =>
        Boolean(candidate) &&
        typeof candidate === "object" &&
        !Array.isArray(candidate) &&
        typeof (candidate as { id?: unknown }).id === "string",
    )
    const nested = findCollectorProjectNode(nestedNodes, nodeId)
    if (nested) return nested
  }
  return undefined
}

function readCollectorOutput(details: Record<string, unknown> | undefined): CollectorOutputV1 | null {
  if (!details) return null
  const candidates = [details.collectorOutput, details.output, details.result, details]
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) continue
    const record = candidate as Record<string, unknown>
    if (!Array.isArray(record.items) || !Array.isArray(record.sourceResults)) continue
    return {
      items: record.items as CollectorOutputV1["items"],
      sourceResults: record.sourceResults as CollectorOutputV1["sourceResults"],
    }
  }
  return null
}
