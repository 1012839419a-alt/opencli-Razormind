import type { WorkflowNodeCatalogItem } from "./node-catalog"
import { workflowRequestAuthHeaders } from "./request-auth"

type ApiResponse<T> = {
  success?: boolean
  data?: T
  error?: string
  message?: string
}

export type WorkflowOpenTabsToolNodeArg = {
  name: string
  type?: string | null
  required: boolean
  valueRequired: boolean
  choices: unknown[]
  default?: unknown
  help?: string | null
}

export type WorkflowOpenTabsToolNode = {
  id: string
  label: string
  description: string
  status: "runnable" | "blocked" | "preview_only" | "design_only"
  plugin: string
  tool: string
  access: "read" | "write"
  requiredArgs: string[]
  args: WorkflowOpenTabsToolNodeArg[]
  inputSchema: Record<string, unknown>
  params: Record<string, unknown>
  manifest: Record<string, unknown>
}

export type WorkflowOpenTabsToolNodesResponse = {
  available: boolean
  total: number
  summary: Record<string, unknown>
  reason?: string | null
  nodes: WorkflowOpenTabsToolNode[]
}

export async function fetchWorkflowOpenTabsToolNodes(
  options: {
    authorization?: string | null
    plugin?: string
    q?: string
    includeWrite?: boolean
    limit?: number
    signal?: AbortSignal
  } = {},
): Promise<WorkflowOpenTabsToolNodesResponse> {
  const params = new URLSearchParams()
  if (options.plugin) params.set("plugin", options.plugin)
  if (options.q) params.set("q", options.q)
  if (typeof options.includeWrite === "boolean") {
    params.set("includeWrite", String(options.includeWrite))
  }
  if (typeof options.limit === "number") params.set("limit", String(options.limit))
  const query = params.toString()
  const response = await fetch(`/api/workflow/opentabs-tool-nodes${query ? `?${query}` : ""}`, {
    headers: {
      ...workflowRequestAuthHeaders(options.authorization),
    },
    cache: "no-store",
    signal: options.signal,
  })
  const payload = (await response.json().catch(() => null)) as ApiResponse<WorkflowOpenTabsToolNodesResponse> | null
  if (!response.ok || !payload?.data) {
    throw new Error(payload?.message ?? payload?.error ?? `OpenTabs tool fetch failed (${response.status})`)
  }
  return payload.data
}

export function workflowCatalogItemForOpenTabsToolNode(
  node: WorkflowOpenTabsToolNode,
  values: Record<string, string> = {},
): WorkflowNodeCatalogItem {
  const isWrite = node.access !== "read"
  const toolParams: Record<string, unknown> = {}
  for (const arg of node.args) {
    const rawValue = values[arg.name]
    if (rawValue === undefined || rawValue === "") continue
    toolParams[arg.name] = parseArgumentValue(rawValue, arg.type)
  }
  return {
    id: "external.tool.capability",
    idPrefix: `action-opentabs-${safeIdPart(node.plugin)}-${safeIdPart(node.tool)}`,
    label: node.label,
    description: node.description || `调用 OpenTabs 工具 ${node.tool}`,
    category: "output",
    profile: "intelligence",
    kind: "action",
    capability: "store",
    icon: "Wrench",
    color: isWrite ? "var(--chart-3)" : "var(--chart-4)",
    params: {
      ...node.params,
      toolParams,
      opentabsToolNodeId: node.id,
      opentabsAccess: node.access,
    },
    proposalState: isWrite ? "accepted" : undefined,
    agentPermissionPatch: isWrite
      ? { canFetchNetwork: true, canMutateExternalSites: true }
      : { canFetchNetwork: true },
    keywords: [
      "opentabs",
      "browser",
      "浏览器",
      "工具",
      node.plugin,
      node.tool,
      node.access,
      node.label,
      node.description,
    ].filter(Boolean),
  }
}

function parseArgumentValue(value: string, type?: string | null): unknown {
  const normalizedType = (type ?? "").toLowerCase()
  if (normalizedType === "boolean" || normalizedType === "bool") return value === "true"
  if (["integer", "int", "number", "float"].includes(normalizedType)) {
    const parsed = Number(value)
    return Number.isNaN(parsed) ? value : parsed
  }
  if (normalizedType === "object" || normalizedType === "array") {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }
  return value
}

function safeIdPart(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "tool"
}
