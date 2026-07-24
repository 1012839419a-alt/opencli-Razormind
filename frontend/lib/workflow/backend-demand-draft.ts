import {
  getCollectorNodeRevision,
  parseCollectorNodeProposal,
  type AgentProposal,
  type AgentProposalOperation,
  type CollectorNodeProposal,
  type CollectorPatchOperation,
} from "./proposal"
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
  const payload = await requestWorkflowDemand(project, text, options)
  return toAgentProposal(payload, text)
}

export async function draftCollectorNodeDemand(
  project: WorkflowProject,
  nodeId: string,
  text: string,
  options: { authorization?: string | null; locale?: string | null } = {},
): Promise<CollectorNodeProposal> {
  const payload = await requestWorkflowDemand(project, text, options)
  return toCollectorNodeProposal(payload, project, nodeId, text)
}

async function requestWorkflowDemand(
  project: WorkflowProject,
  text: string,
  options: { authorization?: string | null; locale?: string | null },
): Promise<BackendWorkflowPatchResponse> {
  const response = await fetch("/api/workflow/demand-draft", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.authorization ? { Authorization: options.authorization } : {}),
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
  return payload.data
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

function toCollectorNodeProposal(
  response: BackendWorkflowPatchResponse,
  project: WorkflowProject,
  nodeId: string,
  text: string,
): CollectorNodeProposal {
  const node = project.nodes.find((candidate) => candidate.id === nodeId)
  if (!node) throw new Error(`Collector proposal target "${nodeId}" does not exist`)

  const parameterPatches = response.patch.operations.filter(
    (operation) => operation.op === "update_parameters" && operation.nodeId === nodeId,
  )
  if (parameterPatches.length === 0) {
    throw new Error(`Demand draft did not return a structured patch for collector node "${nodeId}"`)
  }
  const desiredParams = Object.assign({}, ...parameterPatches.map((operation) => operation.params ?? {}))
  const operations = collectorOperationsFromParams(node.params, desiredParams)
  if (operations.length === 0) {
    throw new Error("Demand draft did not change any Agent-editable collector fields")
  }
  return parseCollectorNodeProposal({
    proposalId: `collector-demand-${Date.now()}`,
    nodeId,
    baseRevision: getCollectorNodeRevision(node),
    summary: `Update collector: ${text.slice(0, 64)}`,
    operations,
  })
}

function collectorOperationsFromParams(
  currentParams: Record<string, unknown>,
  desiredParams: Record<string, unknown>,
): CollectorPatchOperation[] {
  const operations: CollectorPatchOperation[] = []
  if ("sources" in desiredParams) {
    if (!Array.isArray(desiredParams.sources)) {
      throw new Error("Collector demand patch params.sources must be an array")
    }
    const currentSources = Array.isArray(currentParams.sources)
      ? currentParams.sources.map(asRecord)
      : []
    const desiredSources = desiredParams.sources.map(asRecord)
    const desiredIds = new Set(desiredSources.map(sourceId))
    for (const source of currentSources) {
      const id = sourceId(source)
      if (!desiredIds.has(id)) {
        operations.push({ type: "removeSource", sourceId: id, expectedSource: source })
      }
    }
    for (const desired of desiredSources) {
      const id = sourceId(desired)
      const current = currentSources.find((source) => sourceId(source) === id)
      if (!current) {
        operations.push({ type: "addSource", source: desired })
        continue
      }
      const changes: Record<string, unknown> = {}
      const expected: Record<string, { exists: boolean; value?: unknown }> = {}
      for (const [key, value] of Object.entries(desired)) {
        if (key === "sourceId" || key === "kind" || deepEqual(current[key], value)) continue
        changes[key] = value
        expected[key] = key in current ? { exists: true, value: current[key] } : { exists: false }
      }
      if (Object.keys(changes).length > 0) {
        operations.push({ type: "updateSource", sourceId: id, changes, expected })
      }
    }

    const simulatedOrder = currentSources
      .map(sourceId)
      .filter((id) => desiredIds.has(id))
    for (const desired of desiredSources) {
      const id = sourceId(desired)
      if (!simulatedOrder.includes(id)) simulatedOrder.push(id)
    }
    desiredSources.map(sourceId).forEach((id, toIndex) => {
      const expectedIndex = simulatedOrder.indexOf(id)
      if (expectedIndex === toIndex) return
      operations.push({ type: "moveSource", sourceId: id, expectedIndex, toIndex })
      simulatedOrder.splice(expectedIndex, 1)
      simulatedOrder.splice(toIndex, 0, id)
    })
  }

  if ("execution" in desiredParams) {
    const desiredExecution = asRecord(desiredParams.execution)
    const currentExecution = isRecord(currentParams.execution) ? currentParams.execution : {}
    for (const field of ["concurrency", "timeoutMs", "retry"] as const) {
      if (!(field in desiredExecution) || deepEqual(currentExecution[field], desiredExecution[field])) continue
      operations.push({
        type: "setExecution",
        field,
        value: desiredExecution[field],
        expected: field in currentExecution
          ? { exists: true, value: currentExecution[field] }
          : { exists: false },
      })
    }
  }
  return operations
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new Error("Collector demand patch contains a non-object structured value")
  return value
}

function sourceId(source: Record<string, unknown>): string {
  if (typeof source.sourceId !== "string" || source.sourceId.length === 0) {
    throw new Error("Collector demand patch source requires a stable sourceId")
  }
  return source.sourceId
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function deepEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}
