import {
  getCollectorNodeRevision,
  type AgentProposal,
  type AgentProposalOperation,
  type CollectorNodeProposal,
  type CollectorPatchOperation,
} from "./proposal"
import { workflowRequestAuthHeaders } from "./request-auth"
import type { WorkflowProject, WorkflowProjectEdge, WorkflowProjectNode } from "./schema"

type ApiResponse<T> = {
  success?: boolean
  data?: T
  error?: string
  message?: string
}

type BackendPatchOperation = {
  op: string
  node?: WorkflowProjectNode
  edge?: WorkflowProjectEdge
  nodeId?: string
  params?: Record<string, unknown>
  capability?: string
  reason?: string
}

type BackendWorkflowPatchResponse = {
  valid: boolean
  errors: Array<{ code: string; message: string; node_id?: string | null; edge_id?: string | null }>
  missing_capabilities: Array<{ capability: string; reason?: string | null; n8n_search_hint?: string | null }>
  patch: { operations: BackendPatchOperation[] }
  project?: WorkflowProject | null
  compile?: unknown
}

export async function draftWorkflowDemand(
  project: WorkflowProject,
  text: string,
  options: { authorization?: string | null; locale?: string | null } = {},
): Promise<AgentProposal> {
  const response = await fetch("/api/workflow/demand-draft", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...workflowRequestAuthHeaders(options.authorization),
    },
    body: JSON.stringify({
      project,
      text,
      ...(options.locale ? { locale: options.locale } : {}),
    }),
  })
  const payload = (await response.json().catch(() => null)) as ApiResponse<BackendWorkflowPatchResponse> | null
  if (!response.ok || !payload?.data) {
    throw new Error(payload?.message ?? payload?.error ?? `Workflow demand draft failed (${response.status})`)
  }
  return toAgentProposal(payload.data, text)
}

function toAgentProposal(response: BackendWorkflowPatchResponse, text: string): AgentProposal {
  const operations = response.patch.operations.flatMap(toAgentOperation)
  if (operations.length === 0) {
    const missing = response.missing_capabilities[0]
    throw new Error(missing?.reason ?? missing?.capability ?? "No existing capability can assemble this demand")
  }
  return {
    id: `demand-${Date.now()}`,
    title: `Assemble: ${text.slice(0, 48)}`,
    summary: "Existing runtime capabilities were assembled into a reviewable WorkflowProject patch.",
    risk: response.valid && response.errors.length === 0 ? "low" : "medium",
    validationEvidence: [
      {
        id: "demand-mapped-existing-capability",
        label: "Existing capability mapped",
        passed: response.missing_capabilities.length === 0,
        details: response.missing_capabilities.map((item) => item.capability).join(", ") || "OpenCLI HDA/source slots",
      },
      {
        id: "demand-backend-compile",
        label: "Backend compile",
        passed: response.valid,
        details: response.errors.map((error) => error.message).join("; ") || "Patch compiles",
      },
    ],
    operations,
  }
}

export async function draftCollectorNodeDemand(
  project: WorkflowProject,
  nodeId: string,
  text: string,
  options: { authorization?: string | null; locale?: string | null } = {},
): Promise<CollectorNodeProposal> {
  const node = findProjectNode(project.nodes, nodeId)
  if (!node) throw new Error(`Collector demand target "${nodeId}" does not exist`)
  const response = await fetch("/api/workflow/demand-draft", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...workflowRequestAuthHeaders(options.authorization),
    },
    body: JSON.stringify({
      project,
      text,
      ...(options.locale ? { locale: options.locale } : {}),
    }),
  })
  const payload = (await response.json().catch(() => null)) as ApiResponse<BackendWorkflowPatchResponse> | null
  if (!response.ok || !payload?.data) {
    throw new Error(payload?.message ?? payload?.error ?? `Collector demand draft failed (${response.status})`)
  }
  const operations = toCollectorOperations(payload.data.patch.operations, node)
  if (operations.length === 0) {
    throw new Error(payload.data.missing_capabilities[0]?.reason ?? "No collector changes were proposed")
  }
  return {
    proposalId: `collector-demand-${Date.now()}`,
    nodeId,
    baseRevision: getCollectorNodeRevision(node),
    summary: `Update collector from demand: ${text.slice(0, 120)}`,
    operations,
  }
}

function toAgentOperation(operation: BackendPatchOperation): AgentProposalOperation[] {
  if (operation.op === "add_node" && operation.node) {
    return [{ type: "addNode", node: operation.node }]
  }
  if (operation.op === "update_parameters" && operation.nodeId) {
    return [{ type: "updateNodeParams", nodeId: operation.nodeId, params: operation.params ?? {} }]
  }
  if (operation.op === "connect_nodes" && operation.edge) {
    return [{ type: "addEdge", edge: operation.edge }]
  }
  return []
}

function toCollectorOperations(
  operations: BackendPatchOperation[],
  node: WorkflowProjectNode,
): CollectorPatchOperation[] {
  const currentSources = Array.isArray(node.params.sources) ? node.params.sources : []
  return operations.flatMap((operation) => {
    if (operation.op !== "update_parameters" || operation.nodeId !== node.id) return []
    const nextParams = operation.params ?? {}
    const nextSources = Array.isArray(nextParams.sources) ? nextParams.sources : []
    const changes: CollectorPatchOperation[] = []
    for (const nextSource of nextSources) {
      if (!nextSource || typeof nextSource !== "object" || Array.isArray(nextSource)) continue
      const source = nextSource as Record<string, unknown>
      const sourceId = typeof source.sourceId === "string" ? source.sourceId : null
      if (!sourceId) continue
      const previous = currentSources.find((candidate) => (
        Boolean(candidate) &&
        typeof candidate === "object" &&
        !Array.isArray(candidate) &&
        (candidate as Record<string, unknown>).sourceId === sourceId
      ))
      if (!previous || typeof previous !== "object" || Array.isArray(previous)) continue
      for (const [key, value] of Object.entries(source)) {
        if (key === "sourceId" || key === "kind") continue
        if (JSON.stringify((previous as Record<string, unknown>)[key]) === JSON.stringify(value)) continue
        changes.push({
          type: "updateSource",
          sourceId,
          changes: { [key]: value },
          expected: {
            [key]: {
              exists: key in (previous as Record<string, unknown>),
              value: (previous as Record<string, unknown>)[key],
            },
          },
        })
      }
    }
    const nextExecution = nextParams.execution
    if (nextExecution && typeof nextExecution === "object" && !Array.isArray(nextExecution)) {
      const currentExecution = node.params.execution
      const previous = currentExecution && typeof currentExecution === "object" && !Array.isArray(currentExecution)
        ? currentExecution as Record<string, unknown>
        : {}
      for (const [field, value] of Object.entries(nextExecution)) {
        if (field !== "concurrency" && field !== "timeoutMs" && field !== "retry") continue
        if (JSON.stringify(previous[field]) === JSON.stringify(value)) continue
        changes.push({
          type: "setExecution",
          field,
          value,
          expected: { exists: field in previous, value: previous[field] },
        })
      }
    }
    return changes
  })
}

function findProjectNode(
  nodes: WorkflowProjectNode[],
  nodeId: string,
): WorkflowProjectNode | undefined {
  for (const node of nodes) {
    if (node.id === nodeId) return node
    const nestedNodes = (node.internals?.nodes ?? []).filter(
      (candidate): candidate is WorkflowProjectNode =>
        Boolean(candidate) &&
        typeof candidate === "object" &&
        !Array.isArray(candidate) &&
        typeof (candidate as { id?: unknown }).id === "string",
    )
    const nested = findProjectNode(nestedNodes, nodeId)
    if (nested) return nested
  }
  return undefined
}
