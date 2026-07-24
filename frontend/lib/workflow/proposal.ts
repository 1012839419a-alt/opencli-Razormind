import { z } from "zod"
import {
  parseWorkflowProject,
  workflowEdgeSchema,
  workflowNodeSchema,
  workflowSettingsSchema,
  type WorkflowProject,
  type WorkflowProjectEdge,
  type WorkflowProjectNode,
} from "./schema"

const jsonRecordSchema = z.record(z.string(), z.unknown())
const collectorSourceKindSchema = z.enum(["web", "api", "rss", "cli"])
const collectorExpectedValueSchema = z.object({
  exists: z.boolean(),
  value: z.unknown().optional(),
})

const COLLECTOR_SOURCE_FIELDS = {
  web: new Set(["sourceId", "kind", "name", "enabled", "url", "fetchMode", "selector", "extraction", "pagination", "timeWindow"]),
  api: new Set(["sourceId", "kind", "name", "enabled", "credentialRef", "credentialScheme", "url", "method", "query", "headers", "body", "pagination", "responseMapping"]),
  rss: new Set(["sourceId", "kind", "name", "enabled", "feedUrl", "timeWindow", "itemLimit"]),
  cli: new Set(["sourceId", "kind", "name", "enabled", "adapterNodeId", "args"]),
} satisfies Record<z.infer<typeof collectorSourceKindSchema>, Set<string>>

const FORBIDDEN_COLLECTOR_KEYS = new Set([
  "apikey",
  "xapikey",
  "accesstoken",
  "refreshtoken",
  "authtoken",
  "bearertoken",
  "clientsecret",
  "secret",
  "shell",
  "commandline",
  "scripttext",
  "rawcommand",
  "token",
  "password",
  "cookie",
  "authorization",
])

const collectorSourceSchema = jsonRecordSchema.superRefine((source, context) => {
  const sourceId = source.sourceId
  const parsedKind = collectorSourceKindSchema.safeParse(source.kind)
  if (typeof sourceId !== "string" || sourceId.length === 0) {
    context.addIssue({ code: "custom", message: "Collector source requires a stable sourceId" })
  }
  if (!parsedKind.success) {
    context.addIssue({ code: "custom", message: "Collector source kind must be web, api, rss, or cli" })
    return
  }
  for (const key of Object.keys(source)) {
    if (!COLLECTOR_SOURCE_FIELDS[parsedKind.data].has(key)) {
      context.addIssue({ code: "custom", message: `Collector ${parsedKind.data} source field "${key}" is not editable by Agent` })
    }
  }
  addForbiddenKeyIssues(source, context)
})

const collectorSourceChangesSchema = jsonRecordSchema.superRefine((changes, context) => {
  if ("sourceId" in changes || "kind" in changes) {
    context.addIssue({ code: "custom", message: "Collector sourceId and kind cannot be changed by a patch" })
  }
  addForbiddenKeyIssues(changes, context)
})

export const collectorPatchOperationSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("addSource"),
    source: collectorSourceSchema,
    index: z.number().int().nonnegative().optional(),
  }),
  z.object({
    type: z.literal("updateSource"),
    sourceId: z.string().min(1),
    changes: collectorSourceChangesSchema,
    expected: z.record(z.string(), collectorExpectedValueSchema),
  }).superRefine((operation, context) => {
    for (const key of Object.keys(operation.changes)) {
      if (!(key in operation.expected)) {
        context.addIssue({ code: "custom", message: `Collector updateSource requires expected state for "${key}"` })
      }
    }
  }),
  z.object({
    type: z.literal("removeSource"),
    sourceId: z.string().min(1),
    expectedSource: collectorSourceSchema,
  }),
  z.object({
    type: z.literal("moveSource"),
    sourceId: z.string().min(1),
    toIndex: z.number().int().nonnegative(),
    expectedIndex: z.number().int().nonnegative(),
  }),
  z.object({
    type: z.literal("setExecution"),
    field: z.enum(["concurrency", "timeoutMs", "retry"]),
    value: z.unknown(),
    expected: collectorExpectedValueSchema,
  }),
])

export const collectorNodeProposalSchema = z.object({
  proposalId: z.string().min(1),
  nodeId: z.string().min(1),
  baseRevision: z.string().min(1),
  summary: z.string().min(1),
  operations: z.array(collectorPatchOperationSchema).min(1),
})

export const agentProposalRiskLabelSchema = z.enum(["low", "medium", "high"])

export const agentProposalValidationEvidenceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  passed: z.boolean(),
  details: z.string().optional(),
})

export const addNodeOperationSchema = z.object({
  type: z.literal("addNode"),
  node: workflowNodeSchema,
})

export const updateNodeParamsOperationSchema = z.object({
  type: z.literal("updateNodeParams"),
  nodeId: z.string().min(1),
  params: jsonRecordSchema,
})

export const removeNodeOperationSchema = z.object({
  type: z.literal("removeNode"),
  nodeId: z.string().min(1),
})

export const addEdgeOperationSchema = z.object({
  type: z.literal("addEdge"),
  edge: workflowEdgeSchema,
})

export const removeEdgeOperationSchema = z.object({
  type: z.literal("removeEdge"),
  edgeId: z.string().min(1),
})

export const updateProjectSettingsOperationSchema = z.object({
  type: z.literal("updateProjectSettings"),
  settings: workflowSettingsSchema.partial(),
})

export const updateProfileRubricOperationSchema = z.object({
  type: z.literal("updateProfileRubric"),
  rubric: jsonRecordSchema,
})

export const agentProposalOperationSchema = z.discriminatedUnion("type", [
  addNodeOperationSchema,
  updateNodeParamsOperationSchema,
  removeNodeOperationSchema,
  addEdgeOperationSchema,
  removeEdgeOperationSchema,
  updateProjectSettingsOperationSchema,
  updateProfileRubricOperationSchema,
])

export const agentProposalSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  summary: z.string().optional(),
  risk: agentProposalRiskLabelSchema,
  validationEvidence: z.array(agentProposalValidationEvidenceSchema).default([]),
  operations: z.array(agentProposalOperationSchema).min(1),
})

export type AgentProposalRiskLabel = z.infer<typeof agentProposalRiskLabelSchema>
export type AgentProposalValidationEvidence = z.infer<typeof agentProposalValidationEvidenceSchema>
export type AgentProposalOperation = z.infer<typeof agentProposalOperationSchema>
export type AgentProposal = z.infer<typeof agentProposalSchema>
export type CollectorPatchOperation = z.infer<typeof collectorPatchOperationSchema>
export type CollectorNodeProposal = z.infer<typeof collectorNodeProposalSchema>
export type WorkflowProjectDraft = WorkflowProject & {
  profileRubric?: Record<string, unknown>
}

export type CollectorProposalDifference = {
  index: number
  type: CollectorPatchOperation["type"]
  path: string
  before: unknown
  after: unknown
  status: "change" | "unchanged" | "conflict"
  message?: string
}

export type CollectorProposalDecision = {
  status: "accepted" | "rebased" | "conflict" | "rejected"
  project: WorkflowProjectDraft
  proposal: CollectorNodeProposal
  differences: CollectorProposalDifference[]
  conflicts: string[]
  changed: boolean
}

export function parseAgentProposal(input: unknown): AgentProposal {
  return agentProposalSchema.parse(input)
}

export function parseCollectorNodeProposal(input: unknown): CollectorNodeProposal {
  return collectorNodeProposalSchema.parse(input)
}

export function getCollectorNodeRevision(node: WorkflowProjectNode): string {
  const input = stableJson({
    id: node.id,
    kind: node.kind,
    capability: node.capability,
    adapter: node.adapter ?? null,
    catalogId: typeof node.ui?.catalogId === "string" ? node.ui.catalogId : null,
    params: node.params,
  })
  let hash = 0x811c9dc5
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `collector-v1-${(hash >>> 0).toString(16).padStart(8, "0")}`
}

export function previewCollectorNodeProposal(
  project: WorkflowProjectDraft,
  proposalInput: unknown,
): CollectorProposalDifference[] {
  const proposal = parseCollectorNodeProposal(proposalInput)
  const draft = cloneProjectDraft(project)
  const node = findNode(draft, proposal.nodeId)
  return evaluateCollectorOperations(node, proposal.operations, false).differences
}

export function acceptCollectorNodeProposal(
  project: WorkflowProjectDraft,
  proposalInput: unknown,
): CollectorProposalDecision {
  const proposal = parseCollectorNodeProposal(proposalInput)
  const draft = cloneProjectDraft(project)
  const node = findNode(draft, proposal.nodeId)
  const actualRevision = getCollectorNodeRevision(node)
  const evaluation = evaluateCollectorOperations(node, proposal.operations, true)
  if (evaluation.conflicts.length > 0) {
    return {
      status: "conflict",
      project,
      proposal,
      differences: evaluation.differences,
      conflicts: evaluation.conflicts,
      changed: false,
    }
  }

  const changed = stableJson(project) !== stableJson(draft)
  return {
    status: actualRevision === proposal.baseRevision ? "accepted" : "rebased",
    project: changed ? parseWorkflowProjectDraft(draft) : project,
    proposal: actualRevision === proposal.baseRevision ? proposal : { ...proposal, baseRevision: actualRevision },
    differences: evaluation.differences,
    conflicts: [],
    changed,
  }
}

export function rejectCollectorNodeProposal(
  project: WorkflowProjectDraft,
  proposalInput: unknown,
): CollectorProposalDecision {
  const proposal = parseCollectorNodeProposal(proposalInput)
  return {
    status: "rejected",
    project,
    proposal,
    differences: previewCollectorNodeProposal(project, proposal),
    conflicts: [],
    changed: false,
  }
}

export function acceptAgentProposal(project: WorkflowProjectDraft, proposalInput: unknown): WorkflowProjectDraft {
  const proposal = parseAgentProposal(proposalInput)
  const draft = cloneProjectDraft(project)

  for (const operation of proposal.operations) {
    applyOperation(draft, operation)
  }

  return parseWorkflowProjectDraft(draft)
}

export function rejectAgentProposal(project: WorkflowProjectDraft): WorkflowProjectDraft {
  return project
}

function applyOperation(draft: WorkflowProjectDraft, operation: AgentProposalOperation): void {
  switch (operation.type) {
    case "addNode":
      ensureMissingNode(draft, operation.node.id)
      draft.nodes.push(operation.node)
      return
    case "updateNodeParams":
      findNode(draft, operation.nodeId).params = {
        ...findNode(draft, operation.nodeId).params,
        ...operation.params,
      }
      return
    case "removeNode":
      findNode(draft, operation.nodeId)
      draft.nodes = draft.nodes.filter((node) => node.id !== operation.nodeId)
      draft.edges = draft.edges.filter(
        (edge) => edge.source !== operation.nodeId && edge.target !== operation.nodeId,
      )
      return
    case "addEdge":
      ensureMissingEdge(draft, operation.edge.id)
      ensureNodeExists(draft, operation.edge.source, `source "${operation.edge.source}"`)
      ensureNodeExists(draft, operation.edge.target, `target "${operation.edge.target}"`)
      draft.edges.push(operation.edge)
      return
    case "removeEdge":
      findEdge(draft, operation.edgeId)
      draft.edges = draft.edges.filter((edge) => edge.id !== operation.edgeId)
      return
    case "updateProjectSettings":
      draft.settings = {
        ...draft.settings,
        ...operation.settings,
      }
      return
    case "updateProfileRubric":
      draft.profileRubric = {
        ...draft.profileRubric,
        ...operation.rubric,
      }
      return
  }
}

function evaluateCollectorOperations(
  node: WorkflowProjectNode,
  operations: CollectorPatchOperation[],
  apply: boolean,
): { differences: CollectorProposalDifference[]; conflicts: string[] } {
  const working = apply ? node : structuredClone(node)
  const differences: CollectorProposalDifference[] = []
  const conflicts: string[] = []

  for (const [index, operation] of operations.entries()) {
    const outcome = applyCollectorOperation(working, operation, index)
    differences.push(outcome.difference)
    if (outcome.conflict) conflicts.push(outcome.conflict)
  }
  return { differences, conflicts }
}

function applyCollectorOperation(
  node: WorkflowProjectNode,
  operation: CollectorPatchOperation,
  index: number,
): { difference: CollectorProposalDifference; conflict?: string } {
  const sources = collectorSources(node)
  const conflict = (path: string, before: unknown, after: unknown, message: string) => ({
    difference: { index, type: operation.type, path, before, after, status: "conflict" as const, message },
    conflict: message,
  })
  const changed = (path: string, before: unknown, after: unknown) => ({
    difference: {
      index,
      type: operation.type,
      path,
      before,
      after,
      status: deepEqual(before, after) ? "unchanged" as const : "change" as const,
    },
  })

  switch (operation.type) {
    case "addSource": {
      const expectedKind = collectorNodeKind(node)
      if (expectedKind && operation.source.kind !== expectedKind) {
        return conflict(
          `/nodes/${node.id}/params/sources/${operation.source.sourceId}`,
          undefined,
          operation.source,
          `Collector ${expectedKind} node cannot accept a ${String(operation.source.kind)} source`,
        )
      }
      const existing = sources.find((source) => source.sourceId === operation.source.sourceId)
      if (existing) {
        if (deepEqual(existing, operation.source)) {
          return changed(`/nodes/${node.id}/params/sources/${operation.source.sourceId}`, existing, existing)
        }
        return conflict(
          `/nodes/${node.id}/params/sources/${operation.source.sourceId}`,
          existing,
          operation.source,
          `Collector source "${operation.source.sourceId}" already exists with different content`,
        )
      }
      const targetIndex = Math.min(operation.index ?? sources.length, sources.length)
      sources.splice(targetIndex, 0, operation.source)
      node.params.sources = sources
      return changed(`/nodes/${node.id}/params/sources/${operation.source.sourceId}`, undefined, operation.source)
    }
    case "updateSource": {
      const source = sources.find((candidate) => candidate.sourceId === operation.sourceId)
      if (!source) {
        return conflict(
          `/nodes/${node.id}/params/sources/${operation.sourceId}`,
          undefined,
          operation.changes,
          `Collector source "${operation.sourceId}" no longer exists`,
        )
      }
      const kind = collectorSourceKindSchema.safeParse(source.kind)
      if (!kind.success) {
        return conflict(
          `/nodes/${node.id}/params/sources/${operation.sourceId}`,
          source,
          operation.changes,
          `Collector source "${operation.sourceId}" has an unsupported kind`,
        )
      }
      for (const key of Object.keys(operation.changes)) {
        if (!COLLECTOR_SOURCE_FIELDS[kind.data].has(key)) {
          return conflict(
            `/nodes/${node.id}/params/sources/${operation.sourceId}/${key}`,
            source[key],
            operation.changes[key],
            `Collector ${kind.data} source field "${key}" is not editable by Agent`,
          )
        }
        const expected = operation.expected[key]
        const currentMatchesExpected = expected.exists
          ? key in source && deepEqual(source[key], expected.value)
          : !(key in source)
        if (!currentMatchesExpected && !deepEqual(source[key], operation.changes[key])) {
          return conflict(
            `/nodes/${node.id}/params/sources/${operation.sourceId}/${key}`,
            source[key],
            operation.changes[key],
            `Collector source "${operation.sourceId}" field "${key}" changed since the proposal was created`,
          )
        }
      }
      const before = structuredClone(source)
      Object.assign(source, operation.changes)
      collectorSourceSchema.parse(source)
      return changed(`/nodes/${node.id}/params/sources/${operation.sourceId}`, before, source)
    }
    case "removeSource": {
      const sourceIndex = sources.findIndex((source) => source.sourceId === operation.sourceId)
      if (sourceIndex < 0) {
        return changed(`/nodes/${node.id}/params/sources/${operation.sourceId}`, undefined, undefined)
      }
      const source = sources[sourceIndex]
      if (!deepEqual(source, operation.expectedSource)) {
        return conflict(
          `/nodes/${node.id}/params/sources/${operation.sourceId}`,
          source,
          undefined,
          `Collector source "${operation.sourceId}" changed since the proposal was created`,
        )
      }
      sources.splice(sourceIndex, 1)
      node.params.sources = sources
      return changed(`/nodes/${node.id}/params/sources/${operation.sourceId}`, source, undefined)
    }
    case "moveSource": {
      const sourceIndex = sources.findIndex((source) => source.sourceId === operation.sourceId)
      const targetIndex = Math.min(operation.toIndex, Math.max(0, sources.length - 1))
      if (sourceIndex < 0) {
        return conflict(
          `/nodes/${node.id}/params/sources`,
          sources.map((source) => source.sourceId),
          operation.sourceId,
          `Collector source "${operation.sourceId}" no longer exists`,
        )
      }
      if (sourceIndex !== operation.expectedIndex && sourceIndex !== targetIndex) {
        return conflict(
          `/nodes/${node.id}/params/sources`,
          sources.map((source) => source.sourceId),
          operation.sourceId,
          `Collector source "${operation.sourceId}" order changed since the proposal was created`,
        )
      }
      const before = sources.map((source) => source.sourceId)
      if (sourceIndex !== targetIndex) {
        const [source] = sources.splice(sourceIndex, 1)
        sources.splice(targetIndex, 0, source)
        node.params.sources = sources
      }
      return changed(`/nodes/${node.id}/params/sources`, before, sources.map((source) => source.sourceId))
    }
    case "setExecution": {
      const execution = isJsonRecord(node.params.execution) ? node.params.execution : {}
      const before = execution[operation.field]
      const exists = operation.field in execution
      const matchesExpected = operation.expected.exists
        ? exists && deepEqual(before, operation.expected.value)
        : !exists
      if (!matchesExpected && !deepEqual(before, operation.value)) {
        return conflict(
          `/nodes/${node.id}/params/execution/${operation.field}`,
          before,
          operation.value,
          `Collector execution field "${operation.field}" changed since the proposal was created`,
        )
      }
      validateExecutionValue(operation.field, operation.value)
      execution[operation.field] = operation.value
      node.params.execution = execution
      return changed(`/nodes/${node.id}/params/execution/${operation.field}`, before, operation.value)
    }
  }
}

function collectorSources(node: WorkflowProjectNode): Record<string, unknown>[] {
  if (node.params.sources === undefined) {
    node.params.sources = []
  }
  if (!Array.isArray(node.params.sources)) {
    throw new Error(`Collector node "${node.id}" params.sources must be an array`)
  }
  const expectedKind = collectorNodeKind(node)
  return node.params.sources.map((source) => {
    const parsed = collectorSourceSchema.parse(source)
    if (expectedKind && parsed.kind !== expectedKind) {
      throw new Error(`Collector ${expectedKind} node "${node.id}" contains a ${String(parsed.kind)} source`)
    }
    return source as Record<string, unknown>
  })
}

function collectorNodeKind(node: WorkflowProjectNode): z.infer<typeof collectorSourceKindSchema> | undefined {
  const catalogId = typeof node.ui?.catalogId === "string" ? node.ui.catalogId : ""
  const match = /^collection\.source\.(web|api|rss|cli)$/.exec(catalogId)
  return match ? collectorSourceKindSchema.parse(match[1]) : undefined
}

function validateExecutionValue(field: "concurrency" | "timeoutMs" | "retry", value: unknown): void {
  if (field === "retry") {
    z.object({
      maxAttempts: z.number().int().positive(),
      backoffMs: z.number().int().nonnegative().optional(),
    }).strict().parse(value)
    return
  }
  z.number().int().positive().parse(value)
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`
  if (isJsonRecord(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`
  }
  return JSON.stringify(value)
}

function deepEqual(left: unknown, right: unknown): boolean {
  return stableJson(left) === stableJson(right)
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function addForbiddenKeyIssues(value: unknown, context: z.RefinementCtx, path: PropertyKey[] = []): void {
  if (Array.isArray(value)) {
    value.forEach((item, index) => addForbiddenKeyIssues(item, context, [...path, index]))
    return
  }
  if (!isJsonRecord(value)) return
  for (const [key, nested] of Object.entries(value)) {
    if (FORBIDDEN_COLLECTOR_KEYS.has(normalizeCollectorKey(key))) {
      context.addIssue({ code: "custom", path: [...path, key], message: `Sensitive or executable field "${key}" is forbidden` })
    }
    addForbiddenKeyIssues(nested, context, [...path, key])
  }
}

function normalizeCollectorKey(key: string): string {
  return [...key.toLowerCase()].filter((character) => /[a-z0-9]/.test(character)).join("")
}

function cloneProjectDraft(project: WorkflowProjectDraft): WorkflowProjectDraft {
  return structuredClone(project)
}

function parseWorkflowProjectDraft(project: WorkflowProjectDraft): WorkflowProjectDraft {
  const parsed = parseWorkflowProject(project)
  return project.profileRubric ? { ...parsed, profileRubric: project.profileRubric } : parsed
}

function findNode(project: WorkflowProjectDraft, nodeId: string): WorkflowProjectNode {
  const node = project.nodes.find((candidate) => candidate.id === nodeId)
  if (!node) {
    throw new Error(`Agent proposal operation references missing node "${nodeId}"`)
  }
  return node
}

function findEdge(project: WorkflowProjectDraft, edgeId: string): WorkflowProjectEdge {
  const edge = project.edges.find((candidate) => candidate.id === edgeId)
  if (!edge) {
    throw new Error(`Agent proposal operation references missing edge "${edgeId}"`)
  }
  return edge
}

function ensureMissingNode(project: WorkflowProjectDraft, nodeId: string): void {
  if (project.nodes.some((node) => node.id === nodeId)) {
    throw new Error(`Agent proposal operation would create duplicate node "${nodeId}"`)
  }
}

function ensureMissingEdge(project: WorkflowProjectDraft, edgeId: string): void {
  if (project.edges.some((edge) => edge.id === edgeId)) {
    throw new Error(`Agent proposal operation would create duplicate edge "${edgeId}"`)
  }
}

function ensureNodeExists(project: WorkflowProjectDraft, nodeId: string, label: string): void {
  if (!project.nodes.some((node) => node.id === nodeId)) {
    throw new Error(`Agent proposal operation references missing ${label}`)
  }
}
