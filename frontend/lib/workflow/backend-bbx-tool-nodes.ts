import type { WorkflowNodeCatalogItem } from "./node-catalog"

type ApiResponse<T> = {
  success?: boolean
  data?: T
  error?: string
  message?: string
}

export type WorkflowBbxToolNodeArg = {
  name: string
  type?: string | null
  required: boolean
  valueRequired: boolean
  choices: unknown[]
  default?: unknown
  help?: string | null
}

export type WorkflowBbxToolNode = {
  id: string
  label: string
  description: string
  status: "runnable" | "blocked" | "preview_only" | "design_only"
  group: string
  tool: string
  access: "read" | "write"
  requiredArgs: string[]
  args: WorkflowBbxToolNodeArg[]
  params: Record<string, unknown>
  manifest: Record<string, unknown>
}

export type WorkflowBbxToolNodesResponse = {
  available: boolean
  total: number
  summary: Record<string, unknown>
  reason?: string | null
  nodes: WorkflowBbxToolNode[]
}

export async function fetchWorkflowBbxToolNodes(
  options: {
    authorization?: string | null
    group?: string
    q?: string
    includeWrite?: boolean
    limit?: number
    signal?: AbortSignal
  } = {},
): Promise<WorkflowBbxToolNodesResponse> {
  const params = new URLSearchParams()
  if (options.group) params.set("group", options.group)
  if (options.q) params.set("q", options.q)
  if (typeof options.includeWrite === "boolean") {
    params.set("includeWrite", String(options.includeWrite))
  }
  if (typeof options.limit === "number") params.set("limit", String(options.limit))
  const query = params.toString()
  const response = await fetch(`/api/workflow/bbx-tool-nodes${query ? `?${query}` : ""}`, {
    headers: {
      ...(options.authorization ? { Authorization: options.authorization } : {}),
    },
    cache: "no-store",
    signal: options.signal,
  })
  const payload = (await response.json().catch(() => null)) as ApiResponse<WorkflowBbxToolNodesResponse> | null
  if (!response.ok || !payload?.data) {
    throw new Error(payload?.message ?? payload?.error ?? `BBX tool fetch failed (${response.status})`)
  }
  return payload.data
}

export function workflowCatalogItemForBbxToolNode(
  node: WorkflowBbxToolNode,
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
    idPrefix: `action-bbx-${safeIdPart(node.group)}-${safeIdPart(node.tool)}`,
    label: node.label,
    description: node.description || `通过 Browser Bridge 调用 ${node.tool}`,
    category: "output",
    profile: "intelligence",
    kind: "action",
    capability: "store",
    icon: "Wrench",
    color: isWrite ? "var(--chart-3)" : "var(--chart-4)",
    params: {
      ...node.params,
      toolParams,
      bbxToolNodeId: node.id,
      bbxAccess: node.access,
    },
    proposalState: isWrite ? "accepted" : undefined,
    agentPermissionPatch: isWrite
      ? { canFetchNetwork: true, canMutateExternalSites: true }
      : { canFetchNetwork: true },
    keywords: [
      "bbx",
      "browser bridge",
      "浏览器",
      "工具",
      node.group,
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
