"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useReactFlow } from "@xyflow/react"
import { Loader2, Sparkles, CornerDownLeft, Globe, ArrowLeft, Wrench, Blocks, Database, Package, Search } from "lucide-react"
import { NODE_PALETTE } from "@/lib/flow/palette"
import type { PaletteItem } from "@/lib/flow/types"
import {
  getWorkflowNodeCatalog,
  workflowCatalogItemLocked,
  workflowCatalogPluginProvenance,
  type WorkflowNodeCatalogItem,
} from "@/lib/workflow/node-catalog"
import { getWorkflowPrimitives, type WorkflowPrimitive } from "@/lib/workflow/node-primitives"
import { workflowNodeDepthFromNetworkStack, workflowNodeLayerAtDepth } from "@/lib/workflow/node-hierarchy"
import { groupPrimitivesForNodeMenu } from "@/lib/workflow/node-menu"
import { getIcon } from "@/lib/flow/icons"
import { useFlowStore } from "@/lib/flow/store"
import { useSettingsStore } from "@/lib/flow/settings-store"
import { primitiveRuntimeCapability, runtimeStatusLabel, runtimeStatusTone } from "@/lib/workflow/capabilities"
import { useWorkflowCapabilities } from "@/lib/workflow/use-workflow-capabilities"
import { generateWorkflowLocally } from "@/lib/flow/local-generate"
import { localizeNodeText } from "@/lib/workflow/node-i18n"
import { cn } from "@/lib/utils"
import {
  fetchWorkflowBbxToolNodes,
  workflowCatalogItemForBbxToolNode,
  type WorkflowBbxToolNode,
} from "@/lib/workflow/backend-bbx-tool-nodes"
import {
  fetchWorkflowOpenCLIAdapterNodes,
  workflowCatalogItemForOpenCLIAdapterNode,
  type WorkflowOpenCLIAdapterNode,
} from "@/lib/workflow/backend-opencli-adapter-nodes"
import {
  fetchWorkflowOpenTabsToolNodes,
  workflowCatalogItemForOpenTabsToolNode,
  type WorkflowOpenTabsToolNode,
} from "@/lib/workflow/backend-opentabs-tool-nodes"

const AI_EXAMPLES = [
  "用户注册后发送欢迎邮件，24 小时后如果未激活则再次提醒",
  "监听订单创建事件，校验库存，扣减库存并通知仓库发货",
  "收到客服工单，判断优先级，高优先级转人工，其余自动回复",
]

type SelectorTab = "blocks" | "sources" | "tools" | "start" | "snippets"

const SELECTOR_TABS: Array<[SelectorTab, string]> = [
  ["blocks", "节点"],
  ["sources", "数据源"],
  ["tools", "工具"],
  ["start", "开始"],
  ["snippets", "片段"],
]

export function CommandPalette({
  open,
  onClose,
  onMessage,
  getAnchor,
}: {
  open: boolean
  onClose: () => void
  onMessage?: (msg: string) => void
  getAnchor?: () => { x: number; y: number }
}) {
  const [query, setQuery] = useState("")
  const [selectorTab, setSelectorTab] = useState<SelectorTab>("blocks")
  const [aiMode, setAiMode] = useState(false)
  const [aiPrompt, setAiPrompt] = useState("")
  const [loading, setLoading] = useState(false)
  const [opencliLoading, setOpencliLoading] = useState(false)
  const [opencliNodes, setOpencliNodes] = useState<WorkflowOpenCLIAdapterNode[]>([])
  const [selectedOpenCLI, setSelectedOpenCLI] = useState<WorkflowOpenCLIAdapterNode | null>(null)
  const [opentabsLoading, setOpenTabsLoading] = useState(false)
  const [opentabsLoaded, setOpenTabsLoaded] = useState(false)
  const [opentabsNodes, setOpenTabsNodes] = useState<WorkflowOpenTabsToolNode[]>([])
  const [selectedOpenTabs, setSelectedOpenTabs] = useState<WorkflowOpenTabsToolNode | null>(null)
  const [bbxLoading, setBbxLoading] = useState(false)
  const [bbxLoaded, setBbxLoaded] = useState(false)
  const [bbxNodes, setBbxNodes] = useState<WorkflowBbxToolNode[]>([])
  const [selectedBbx, setSelectedBbx] = useState<WorkflowBbxToolNode | null>(null)
  const [requiredValues, setRequiredValues] = useState<Record<string, string>>({})
  const inputRef = useRef<HTMLInputElement>(null)
  const aiRef = useRef<HTMLTextAreaElement>(null)

  const { screenToFlowPosition } = useReactFlow()
  const addNodeFromPalette = useFlowStore((s) => s.addNodeFromPalette)
  const addPrimitiveNode = useFlowStore((s) => s.addPrimitiveNode)
  const addWorkflowNodeFromCatalog = useFlowStore((s) => s.addWorkflowNodeFromCatalog)
  const applyGeneratedWorkflow = useFlowStore((s) => s.applyGeneratedWorkflow)
  const workflowProfile = useFlowStore((s) => s.workflowProject.profile)
  const networkStackLength = useFlowStore((s) => s.networkStack.length)
  const inNodeNetwork = networkStackLength > 0
  const nodeDepth = workflowNodeDepthFromNetworkStack(networkStackLength)
  const nodeLayer = workflowNodeLayerAtDepth(nodeDepth)
  const language = useSettingsStore((s) => s.language)
  const { capabilities } = useWorkflowCapabilities(open)

  useEffect(() => {
    if (open) {
      setQuery("")
      setSelectorTab("blocks")
      setAiMode(false)
      setAiPrompt("")
      setSelectedOpenCLI(null)
      setSelectedOpenTabs(null)
      setSelectedBbx(null)
      setOpenTabsLoaded(false)
      setBbxLoaded(false)
      setRequiredValues({})
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  useEffect(() => {
    if (!open || opencliNodes.length || opencliLoading) return
    setOpencliLoading(true)
    void fetchWorkflowOpenCLIAdapterNodes({ includeWrite: true, limit: 5000 })
      .then((result) => {
        setOpencliNodes(result.nodes)
      })
      .finally(() => setOpencliLoading(false))
  }, [open, opencliLoading, opencliNodes.length])

  useEffect(() => {
    if (!open || opentabsLoaded || opentabsLoading) return
    setOpenTabsLoading(true)
    void fetchWorkflowOpenTabsToolNodes({ includeWrite: true, limit: 2000 })
      .then((result) => {
        if (result.available) setOpenTabsNodes(result.nodes)
      })
      .catch(() => {
        // OpenTabs is an optional local runtime. Keep the palette quiet when it is offline.
      })
      .finally(() => {
        setOpenTabsLoaded(true)
        setOpenTabsLoading(false)
      })
  }, [open, opentabsLoaded, opentabsLoading])

  useEffect(() => {
    if (!open || bbxLoaded || bbxLoading) return
    setBbxLoading(true)
    void fetchWorkflowBbxToolNodes({ includeWrite: true, limit: 2000 })
      .then((result) => {
        if (result.available) setBbxNodes(result.nodes)
      })
      .catch(() => {
        // Browser Bridge is optional; do not obscure the rest of the node palette.
      })
      .finally(() => {
        setBbxLoaded(true)
        setBbxLoading(false)
      })
  }, [bbxLoaded, bbxLoading, open])

  useEffect(() => {
    if (aiMode) requestAnimationFrame(() => aiRef.current?.focus())
  }, [aiMode])

  const close = useCallback(() => {
    if (!loading) onClose()
  }, [loading, onClose])

  const addOperator = useCallback(
    (item: PaletteItem) => {
      // 优先落在唤出热盒时的光标位置，回退到视口中心
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        })
      addNodeFromPalette(item, position)
      onMessage?.(`已添加节点：${item.label}`)
      onClose()
    },
    [getAnchor, screenToFlowPosition, addNodeFromPalette, onMessage, onClose],
  )

  const addCatalogOperator = useCallback(
    (item: WorkflowNodeCatalogItem) => {
      if (workflowCatalogItemLocked(item)) {
        onMessage?.(item.runtimeCapability?.reason ?? "该插件能力尚未绑定运行适配器")
        return
      }
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        })
      addWorkflowNodeFromCatalog(item, position)
      const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
      const status = item.runtimeCapability?.status
      onMessage?.(
        status && status !== "runnable"
          ? `已添加一级业务节点：${text.label} (${runtimeStatusLabel(status)})`
          : `已添加一级业务节点：${text.label}`,
      )
      onClose()
    },
    [getAnchor, screenToFlowPosition, addWorkflowNodeFromCatalog, language, onMessage, onClose],
  )

  const addPrimitive = useCallback(
    (item: WorkflowPrimitive) => {
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        })
      addPrimitiveNode(item, position, primitiveRuntimeCapability(capabilities, item.id))
      const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
      onMessage?.(`已添加底层组件：${text.label}`)
      onClose()
    },
    [getAnchor, screenToFlowPosition, addPrimitiveNode, capabilities, language, onMessage, onClose],
  )

  const addOpenCLIAdapter = useCallback(
    (
      item: WorkflowOpenCLIAdapterNode,
      values: Record<string, string> = {},
      configured = false,
    ) => {
      if (!configured && (item.args.length > 0 || item.access !== "read")) {
        setSelectedOpenCLI(item)
        setRequiredValues(Object.fromEntries(
          item.args
            .filter((arg) => arg.default !== undefined && arg.default !== null)
            .map((arg) => [arg.name, String(arg.default)]),
        ))
        return
      }
      const missing = item.requiredArgs.filter((name) => !values[name]?.trim())
      if (missing.length) {
        setSelectedOpenCLI(item)
        setRequiredValues(values)
        return
      }
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
      })
      addWorkflowNodeFromCatalog(workflowCatalogItemForOpenCLIAdapterNode(item, values), position)
      onMessage?.(
        item.access === "read"
          ? `已添加 OpenCLI 数据源：${item.label}`
          : `已确认并添加 OpenCLI 操作：${item.label}`,
      )
      onClose()
    },
    [addWorkflowNodeFromCatalog, getAnchor, onClose, onMessage, screenToFlowPosition],
  )

  const addOpenTabsTool = useCallback(
    (
      item: WorkflowOpenTabsToolNode,
      values: Record<string, string> = {},
      configured = false,
    ) => {
      if (!configured && (item.args.length > 0 || item.access !== "read")) {
        setSelectedOpenTabs(item)
        setRequiredValues(Object.fromEntries(
          item.args
            .filter((arg) => arg.default !== undefined && arg.default !== null)
            .map((arg) => [arg.name, String(arg.default)]),
        ))
        return
      }
      const missing = item.requiredArgs.filter((name) => !values[name]?.trim())
      if (missing.length) {
        setSelectedOpenTabs(item)
        setRequiredValues(values)
        return
      }
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        })
      addWorkflowNodeFromCatalog(workflowCatalogItemForOpenTabsToolNode(item, values), position)
      onMessage?.(
        item.access === "read"
          ? `已添加 OpenTabs 浏览器工具：${item.label}`
          : `已确认并添加 OpenTabs 操作：${item.label}`,
      )
      onClose()
    },
    [addWorkflowNodeFromCatalog, getAnchor, onClose, onMessage, screenToFlowPosition],
  )

  const addBbxTool = useCallback(
    (
      item: WorkflowBbxToolNode,
      values: Record<string, string> = {},
      configured = false,
    ) => {
      if (!configured && (item.args.length > 0 || item.access !== "read")) {
        setSelectedBbx(item)
        setRequiredValues(Object.fromEntries(
          item.args
            .filter((arg) => arg.default !== undefined && arg.default !== null)
            .map((arg) => [arg.name, String(arg.default)]),
        ))
        return
      }
      const missing = item.requiredArgs.filter((name) => !values[name]?.trim())
      if (missing.length) {
        setSelectedBbx(item)
        setRequiredValues(values)
        return
      }
      const position =
        getAnchor?.() ??
        screenToFlowPosition({
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        })
      addWorkflowNodeFromCatalog(workflowCatalogItemForBbxToolNode(item, values), position)
      onMessage?.(
        item.access === "read"
          ? `已添加 BBX 浏览器工具：${item.label}`
          : `已确认并添加 BBX 操作：${item.label}`,
      )
      onClose()
    },
    [addWorkflowNodeFromCatalog, getAnchor, onClose, onMessage, screenToFlowPosition],
  )

  const generate = useCallback(
    async (text: string) => {
      if (!text.trim() || loading) return
      setLoading(true)
      try {
        const res = await fetch("/api/generate-workflow", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: text }),
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data?.detail ?? "failed")
        applyGeneratedWorkflow(data)
        onMessage?.(`已生成工作流：${data.title ?? "未命名"}`)
      } catch {
        const spec = generateWorkflowLocally(text)
        applyGeneratedWorkflow(spec)
        onMessage?.(`已生成工作流（本地引擎）：${spec.title}`)
      } finally {
        setLoading(false)
        onClose()
      }
    },
    [loading, applyGeneratedWorkflow, onMessage, onClose],
  )

  const q = query.trim().toLowerCase()
  const catalogOperators = inNodeNetwork
    ? []
    : getWorkflowNodeCatalog(workflowProfile, capabilities)
  const matchesCatalogQuery = (item: WorkflowNodeCatalogItem) => {
    if (!q) return true
    const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
    return (
      item.label.toLowerCase().includes(q) ||
      text.label.toLowerCase().includes(q) ||
      (text.description ?? "").toLowerCase().includes(q) ||
      item.kind.toLowerCase().includes(q) ||
      item.capability.toLowerCase().includes(q) ||
      item.keywords.some((keyword) => keyword.toLowerCase().includes(q))
    )
  }
  const blockOperators = catalogOperators.filter(
    (item) => item.category !== "source" && item.category !== "package" && item.category !== "trigger" && matchesCatalogQuery(item),
  )
  const sourceOperators = catalogOperators.filter(
    (item) => item.category === "source" && matchesCatalogQuery(item),
  )
  const startOperators = catalogOperators.filter(
    (item) => item.category === "trigger" && matchesCatalogQuery(item),
  )
  const snippetOperators = catalogOperators.filter(
    (item) => item.category === "package" && matchesCatalogQuery(item),
  )
  const filteredOpenCLINodes = (q
    ? opencliNodes.filter((item) => {
        const haystack = `${item.label} ${item.description} ${item.site} ${item.command}`.toLowerCase()
        return haystack.includes(q)
      })
    : opencliNodes
  ).slice(0, q ? 100 : 24)
  const filteredOpenCLISources = filteredOpenCLINodes.filter((item) => item.access === "read")
  const filteredOpenCLITools = filteredOpenCLINodes.filter((item) => item.access !== "read")
  const filteredOpenTabsNodes = (q
    ? opentabsNodes.filter((item) => {
        const haystack = `${item.label} ${item.description} ${item.plugin} ${item.tool}`.toLowerCase()
        return haystack.includes(q)
      })
    : opentabsNodes
  ).slice(0, q ? 100 : 24)
  const filteredBbxNodes = (q
    ? bbxNodes.filter((item) => {
        const haystack = `${item.label} ${item.description} ${item.group} ${item.tool}`.toLowerCase()
        return haystack.includes(q)
      })
    : bbxNodes
  ).slice(0, q ? 100 : 24)
  const primitiveOperators = (inNodeNetwork ? getWorkflowPrimitives() : []).filter((item) => {
    if (!q) return true
    const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
    return (
      item.label.toLowerCase().includes(q) ||
      text.label.toLowerCase().includes(q) ||
      (text.description ?? "").toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      item.keywords.some((keyword) => keyword.toLowerCase().includes(q))
    )
  })
  const primitiveGroups = groupPrimitivesForNodeMenu(primitiveOperators)
  const auxiliaryOperators = NODE_PALETTE.filter(
    (item) => item.category === "annotation" || item.category === "shape",
  )
  const filteredOperators = q
    ? auxiliaryOperators.filter(
        (i) => i.label.toLowerCase().includes(q) || i.nodeType.toLowerCase().includes(q),
      )
    : auxiliaryOperators

  if (!open) return null

  if (selectedOpenCLI) {
    const missingRequired = selectedOpenCLI.requiredArgs.filter((name) => !requiredValues[name]?.trim())
    return (
      <div className="fixed inset-0 z-50 flex items-start justify-center bg-background/85 pt-[15vh]" role="dialog" aria-modal="true" aria-label="配置 OpenCLI 数据源">
        <form
          className="w-[32rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border bg-popover shadow-2xl"
          onSubmit={(event) => {
            event.preventDefault()
            addOpenCLIAdapter(selectedOpenCLI, requiredValues, true)
          }}
        >
          <div className="flex items-center gap-3 border-b px-4 py-3">
            <button type="button" className="grid size-9 place-items-center rounded-md hover:bg-accent" onClick={() => setSelectedOpenCLI(null)} aria-label="返回数据源列表"><ArrowLeft className="size-4" /></button>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{selectedOpenCLI.label}</div>
              <div className="truncate text-xs text-muted-foreground">
                {selectedOpenCLI.access === "read"
                  ? "配置 OpenCLI 命令参数"
                  : "配置写入操作；确认后将允许此工作流修改外部网站"}
              </div>
            </div>
          </div>
          {selectedOpenCLI.access !== "read" ? (
            <div className="border-b border-warning/30 bg-warning/10 px-4 py-3 text-xs leading-5 text-warning-foreground">
              此操作会修改外部网站。系统不会在添加节点时执行，运行前需要用户确认并使用已登录的浏览器会话。
            </div>
          ) : null}
          <div className="grid max-h-[50vh] gap-3 overflow-y-auto p-4">
            {selectedOpenCLI.args.map((arg) => (
              <label key={arg.name} className="grid gap-1.5 text-xs">
                <span>
                  {arg.name}
                  {arg.required ? <span className="ml-1 text-destructive">*</span> : <span className="ml-1 text-muted-foreground">可选</span>}
                </span>
                {arg.choices.length > 0 ? (
                  <select
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenCLI.requiredArgs[0] === arg.name}
                  >
                    <option value="">请选择</option>
                    {arg.choices.map((choice) => (
                      <option key={String(choice)} value={String(choice)}>{String(choice)}</option>
                    ))}
                  </select>
                ) : ["bool", "boolean"].includes((arg.type ?? "").toLowerCase()) ? (
                  <select
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenCLI.requiredArgs[0] === arg.name}
                  >
                    <option value="">默认</option>
                    <option value="true">是</option>
                    <option value="false">否</option>
                  </select>
                ) : (
                  <input
                    type={["int", "integer", "float", "number"].includes((arg.type ?? "").toLowerCase()) ? "number" : "text"}
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    placeholder={arg.help ?? `输入 ${arg.name}`}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenCLI.requiredArgs[0] === arg.name}
                  />
                )}
                {arg.help ? <span className="text-[10px] leading-4 text-muted-foreground">{arg.help}</span> : null}
              </label>
            ))}
            {selectedOpenCLI.args.length === 0 ? (
              <p className="text-xs text-muted-foreground">这个命令不需要额外参数。</p>
            ) : null}
          </div>
          <div className="flex justify-end gap-2 border-t p-4"><button type="button" className="min-h-10 rounded-md border px-4 text-xs" onClick={() => setSelectedOpenCLI(null)}>取消</button><button type="submit" className="min-h-10 rounded-md bg-primary px-4 text-xs text-primary-foreground disabled:opacity-50" disabled={missingRequired.length > 0}>{selectedOpenCLI.access === "read" ? "添加数据源" : "确认并添加操作"}</button></div>
        </form>
      </div>
    )
  }

  if (selectedOpenTabs) {
    const missingRequired = selectedOpenTabs.requiredArgs.filter((name) => !requiredValues[name]?.trim())
    return (
      <div className="fixed inset-0 z-50 flex items-start justify-center bg-background/85 pt-[15vh]" role="dialog" aria-modal="true" aria-label="配置 OpenTabs 浏览器工具">
        <form
          className="w-[32rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border bg-popover shadow-2xl"
          onSubmit={(event) => {
            event.preventDefault()
            addOpenTabsTool(selectedOpenTabs, requiredValues, true)
          }}
        >
          <div className="flex items-center gap-3 border-b px-4 py-3">
            <button type="button" className="grid size-9 place-items-center rounded-md hover:bg-accent" onClick={() => setSelectedOpenTabs(null)} aria-label="返回工具列表"><ArrowLeft className="size-4" /></button>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{selectedOpenTabs.label}</div>
              <div className="truncate text-xs text-muted-foreground">
                {selectedOpenTabs.access === "read"
                  ? "配置 OpenTabs 浏览器工具参数"
                  : "配置浏览器写入操作；运行时仍受 OpenTabs 权限控制"}
              </div>
            </div>
          </div>
          {selectedOpenTabs.access !== "read" ? (
            <div className="border-b border-warning/30 bg-warning/10 px-4 py-3 text-xs leading-5 text-warning-foreground">
              此操作可能修改当前登录的网站。添加节点不会立即执行；运行时仍需通过工作流确认和 OpenTabs 工具权限。
            </div>
          ) : null}
          <div className="grid max-h-[50vh] gap-3 overflow-y-auto p-4">
            {selectedOpenTabs.args.map((arg) => (
              <label key={arg.name} className="grid gap-1.5 text-xs">
                <span>
                  {arg.name}
                  {arg.required ? <span className="ml-1 text-destructive">*</span> : <span className="ml-1 text-muted-foreground">可选</span>}
                </span>
                {arg.choices.length > 0 ? (
                  <select
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenTabs.requiredArgs[0] === arg.name}
                  >
                    <option value="">请选择</option>
                    {arg.choices.map((choice) => (
                      <option key={String(choice)} value={String(choice)}>{String(choice)}</option>
                    ))}
                  </select>
                ) : ["bool", "boolean"].includes((arg.type ?? "").toLowerCase()) ? (
                  <select
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenTabs.requiredArgs[0] === arg.name}
                  >
                    <option value="">默认</option>
                    <option value="true">是</option>
                    <option value="false">否</option>
                  </select>
                ) : (
                  <input
                    type={["int", "integer", "float", "number"].includes((arg.type ?? "").toLowerCase()) ? "number" : "text"}
                    value={requiredValues[arg.name] ?? ""}
                    onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                    placeholder={arg.help ?? `输入 ${arg.name}`}
                    className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                    autoFocus={selectedOpenTabs.requiredArgs[0] === arg.name}
                  />
                )}
                {arg.help ? <span className="text-[10px] leading-4 text-muted-foreground">{arg.help}</span> : null}
              </label>
            ))}
            {selectedOpenTabs.args.length === 0 ? (
              <p className="text-xs text-muted-foreground">这个浏览器工具不需要额外参数。</p>
            ) : null}
          </div>
          <div className="flex justify-end gap-2 border-t p-4"><button type="button" className="min-h-10 rounded-md border px-4 text-xs" onClick={() => setSelectedOpenTabs(null)}>取消</button><button type="submit" className="min-h-10 rounded-md bg-primary px-4 text-xs text-primary-foreground disabled:opacity-50" disabled={missingRequired.length > 0}>{selectedOpenTabs.access === "read" ? "添加浏览器工具" : "确认并添加操作"}</button></div>
        </form>
      </div>
    )
  }

  if (selectedBbx) {
    const missingRequired = selectedBbx.requiredArgs.filter((name) => !requiredValues[name]?.trim())
    return (
      <div className="fixed inset-0 z-50 flex items-start justify-center bg-background/85 pt-[15vh]" role="dialog" aria-modal="true" aria-label="配置 BBX 浏览器工具">
        <form
          className="w-[32rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border bg-popover shadow-2xl"
          onSubmit={(event) => {
            event.preventDefault()
            addBbxTool(selectedBbx, requiredValues, true)
          }}
        >
          <div className="flex items-center gap-3 border-b px-4 py-3">
            <button type="button" className="grid size-9 place-items-center rounded-md hover:bg-accent" onClick={() => setSelectedBbx(null)} aria-label="返回工具列表"><ArrowLeft className="size-4" /></button>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{selectedBbx.label}</div>
              <div className="truncate text-xs text-muted-foreground">
                {selectedBbx.access === "read"
                  ? "配置 Browser Bridge 调用参数"
                  : "配置浏览器写入操作；运行时需要启用 BBX 页面访问"}
              </div>
            </div>
          </div>
          {selectedBbx.access !== "read" ? (
            <div className="border-b border-warning/30 bg-warning/10 px-4 py-3 text-xs leading-5 text-warning-foreground">
              此操作可能导航、点击或修改当前登录的网站。添加节点不会立即执行；运行时仍需工作流确认并启用 Browser Bridge 访问。
            </div>
          ) : null}
          <div className="grid max-h-[50vh] gap-3 overflow-y-auto p-4">
            {selectedBbx.args.map((arg) => (
              <label key={arg.name} className="grid gap-1.5 text-xs">
                <span>{arg.name}<span className="ml-1 text-muted-foreground">可选</span></span>
                <input
                  type={["int", "integer", "float", "number"].includes((arg.type ?? "").toLowerCase()) ? "number" : "text"}
                  value={requiredValues[arg.name] ?? ""}
                  onChange={(event) => setRequiredValues((current) => ({ ...current, [arg.name]: event.target.value }))}
                  placeholder={arg.help ?? `输入 ${arg.name}`}
                  className="min-h-11 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring/50"
                />
                {arg.help ? <span className="text-[10px] leading-4 text-muted-foreground">{arg.help}</span> : null}
              </label>
            ))}
          </div>
          <div className="flex justify-end gap-2 border-t p-4"><button type="button" className="min-h-10 rounded-md border px-4 text-xs" onClick={() => setSelectedBbx(null)}>取消</button><button type="submit" className="min-h-10 rounded-md bg-primary px-4 text-xs text-primary-foreground disabled:opacity-50" disabled={missingRequired.length > 0}>{selectedBbx.access === "read" ? "添加浏览器工具" : "确认并添加操作"}</button></div>
        </form>
      </div>
    )
  }

  const renderCatalogItems = (items: WorkflowNodeCatalogItem[]) => items.map((item) => {
    const Icon = getIcon(item.icon)
    const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
    const locked = workflowCatalogItemLocked(item)
    const provenance = workflowCatalogPluginProvenance(item)
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => addCatalogOperator(item)}
        disabled={locked}
        title={locked ? item.runtimeCapability?.reason ?? "等待运行适配器" : undefined}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-65 disabled:hover:bg-transparent"
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-lg border bg-muted/35">
          <Icon className="size-4 text-foreground" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{text.label}</span>
          <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
            {provenance
              ? `${provenance.providerKey} · ${provenance.version}`
              : text.description}
          </span>
        </span>
        <span
          className={cn(
            "rounded-[3px] border px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider",
            runtimeStatusTone(item.runtimeCapability?.status),
          )}
          title={item.runtimeCapability?.reason ?? item.capability}
        >
          {runtimeStatusLabel(item.runtimeCapability?.status)}
        </span>
      </button>
    )
  })

  const renderOpenCLIItems = (items: WorkflowOpenCLIAdapterNode[]) => items.map((item) => (
    <button
      key={item.id}
      type="button"
      onClick={() => addOpenCLIAdapter(item)}
      className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
    >
      <span className="grid size-8 shrink-0 place-items-center rounded-lg border bg-muted/35">
        {item.access === "read" ? <Globe className="size-4" /> : <Wrench className="size-4" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{item.label}</span>
        <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
          {item.description || `${item.site} ${item.command}`}
        </span>
      </span>
      <span className={cn(
        "rounded-[3px] border px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-wider",
        item.access !== "read" || item.requiredArgs.length ? "border-warning/40 text-warning" : "border-success/40 text-success",
      )}>
        {item.access !== "read" ? "写入" : item.requiredArgs.length ? `${item.requiredArgs.length} 参数` : "读取"}
      </span>
    </button>
  ))

  const selectFirstVisible = () => {
    if (inNodeNetwork) {
      if (primitiveOperators[0]) addPrimitive(primitiveOperators[0])
      else if (filteredOperators[0]) addOperator(filteredOperators[0])
      return
    }
    if (selectorTab === "blocks") {
      if (blockOperators[0]) addCatalogOperator(blockOperators[0])
      else if (filteredOperators[0]) addOperator(filteredOperators[0])
      return
    }
    if (selectorTab === "sources") {
      if (sourceOperators[0]) addCatalogOperator(sourceOperators[0])
      else if (filteredOpenCLISources[0]) addOpenCLIAdapter(filteredOpenCLISources[0])
      return
    }
    if (selectorTab === "tools") {
      if (filteredOpenCLITools[0]) addOpenCLIAdapter(filteredOpenCLITools[0])
      else if (filteredOpenTabsNodes[0]) addOpenTabsTool(filteredOpenTabsNodes[0])
      else if (filteredBbxNodes[0]) addBbxTool(filteredBbxNodes[0])
      return
    }
    if (selectorTab === "start") {
      if (startOperators[0]) addCatalogOperator(startOperators[0])
      return
    }
    if (snippetOperators[0]) addCatalogOperator(snippetOperators[0])
  }

  const hasTopLevelResults = selectorTab === "blocks"
    ? blockOperators.length + filteredOperators.length > 0
    : selectorTab === "sources"
      ? sourceOperators.length + filteredOpenCLISources.length > 0 || opencliLoading
      : selectorTab === "tools"
        ? filteredOpenCLITools.length + filteredOpenTabsNodes.length + filteredBbxNodes.length > 0 || opentabsLoading || bbxLoading
        : selectorTab === "start"
          ? startOperators.length > 0
          : snippetOperators.length > 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-background/85 pt-[10vh]"
      onClick={close}
      onKeyDown={(e) => {
        if (e.key === "Escape") close()
      }}
      role="dialog"
      aria-modal="true"
      aria-label="节点选择器"
    >
      <div
        className="w-[40rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border bg-popover shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {!aiMode ? (
          <>
            <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
              <div className="flex items-center gap-2">
                {inNodeNetwork ? <Blocks className="size-4 text-muted-foreground" /> : <Package className="size-4 text-muted-foreground" />}
                <div>
                  <div className="text-sm font-semibold">{inNodeNetwork ? `添加 L${nodeDepth} 组件` : "添加节点"}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {inNodeNetwork ? nodeLayer.label : "从已安装 Provider 中选择能力"}
                  </div>
                </div>
              </div>
              {!inNodeNetwork ? (
                <button
                  type="button"
                  onClick={() => setAiMode(true)}
                  className="flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Sparkles className="size-3.5" />
                  AI 生成
                </button>
              ) : null}
            </div>

            {!inNodeNetwork ? (
              <nav aria-label="节点类型" className="flex border-b bg-muted/20 px-2 pt-1">
                {SELECTOR_TABS.map(([key, label]) => {
                  const selected = selectorTab === key
                  return (
                    <button
                      key={key}
                      type="button"
                      aria-current={selected ? "page" : undefined}
                      onClick={() => {
                        setSelectorTab(key)
                        setQuery("")
                        requestAnimationFrame(() => inputRef.current?.focus())
                      }}
                      className={cn(
                        "relative min-h-9 px-3 text-xs font-medium transition-colors",
                        selected ? "text-foreground" : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {label}
                      {selected ? <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-foreground" /> : null}
                    </button>
                  )
                })}
              </nav>
            ) : null}

            <div className="flex items-center gap-2 border-b px-4 py-3">
              {selectorTab === "sources" && !inNodeNetwork ? <Database className="size-4 text-muted-foreground" /> : <Search className="size-4 text-muted-foreground" />}
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                    selectFirstVisible()
                  }
                }}
                placeholder={inNodeNetwork ? "搜索底层组件" : `搜索${SELECTOR_TABS.find(([key]) => key === selectorTab)?.[1] ?? "节点"}`}
                className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
                aria-label="搜索节点"
              />
              <kbd className="rounded-sm border px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                ESC
              </kbd>
            </div>

            <div className="max-h-[58vh] overflow-y-auto py-2">
              {primitiveOperators.length > 0 ? (
                <>
                  <p className="px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">
                    L{nodeDepth} · {nodeLayer.label}
                  </p>
                  {primitiveGroups.map((group) => (
                    <div key={group.category}>
                      <p className="border-y border-border/60 bg-muted/30 px-4 py-1.5 text-[11px] font-medium text-muted-foreground">
                        {group.label}
                      </p>
                      {group.items.map((item) => {
                        const Icon = getIcon(item.icon)
                        const text = localizeNodeText(item.id, { label: item.label, description: item.description }, language)
                        const runtimeCapability = primitiveRuntimeCapability(capabilities, item.id)
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => addPrimitive(item)}
                            className="flex w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-accent"
                          >
                            <Icon className="size-3.5 text-muted-foreground" />
                            <span className="min-w-0 flex-1 truncate text-sm">{text.label}</span>
                            <span
                              className={cn(
                                "rounded-[3px] border px-1 py-0.5 font-mono text-[8px] uppercase tracking-wider",
                                runtimeStatusTone(runtimeCapability?.status ?? "design_only"),
                              )}
                              title={runtimeCapability?.reason ?? item.category}
                            >
                              {runtimeStatusLabel(runtimeCapability?.status ?? "design_only")}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  ))}
                </>
              ) : null}

              {!inNodeNetwork && selectorTab === "blocks" && blockOperators.length > 0 ? (
                <>
                  <p className="px-4 pb-1 pt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">工作流节点</p>
                  {renderCatalogItems(blockOperators)}
                </>
              ) : null}

              {!inNodeNetwork && selectorTab === "sources" ? (
                <>
                  {sourceOperators.length > 0 ? (
                    <>
                      <p className="px-4 pb-1 pt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">内置数据源</p>
                      {renderCatalogItems(sourceOperators)}
                    </>
                  ) : null}
                  {opencliLoading || filteredOpenCLISources.length > 0 ? (
                    <>
                      <p className="flex items-center justify-between px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">
                        <span>OpenCLI Provider</span>
                        <span>{opencliLoading ? "读取中…" : `${filteredOpenCLISources.length} 项`}</span>
                      </p>
                      {opencliLoading
                        ? <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />正在读取 OpenCLI 数据源</div>
                        : renderOpenCLIItems(filteredOpenCLISources)}
                    </>
                  ) : null}
                </>
              ) : null}

              {!inNodeNetwork && selectorTab === "tools" ? (
                <>
                  {filteredOpenCLITools.length > 0 ? (
                    <>
                      <p className="px-4 pb-1 pt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">OpenCLI 工具</p>
                      {renderOpenCLIItems(filteredOpenCLITools)}
                    </>
                  ) : null}
                  {opentabsLoading || filteredOpenTabsNodes.length > 0 ? (
                    <>
                      <p className="flex items-center justify-between px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60"><span>OpenTabs</span><span>{opentabsLoading ? "连接中…" : `${filteredOpenTabsNodes.length} 项`}</span></p>
                      {opentabsLoading ? <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />正在连接 OpenTabs</div> : filteredOpenTabsNodes.map((item) => (
                        <button key={item.id} type="button" onClick={() => addOpenTabsTool(item)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent"><span className="grid size-8 shrink-0 place-items-center rounded-lg border bg-muted/35"><Wrench className="size-4" /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.label}</span><span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{item.description || item.tool}</span></span></button>
                      ))}
                    </>
                  ) : null}
                  {bbxLoading || filteredBbxNodes.length > 0 ? (
                    <>
                      <p className="flex items-center justify-between px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60"><span>Browser Bridge</span><span>{bbxLoading ? "连接中…" : `${filteredBbxNodes.length} 项`}</span></p>
                      {bbxLoading ? <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground"><Loader2 className="size-3.5 animate-spin" />正在连接 Browser Bridge</div> : filteredBbxNodes.map((item) => (
                        <button key={item.id} type="button" onClick={() => addBbxTool(item)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-accent"><span className="grid size-8 shrink-0 place-items-center rounded-lg border bg-muted/35"><Wrench className="size-4" /></span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.label}</span><span className="mt-0.5 block truncate text-[10px] text-muted-foreground">{item.description || item.tool}</span></span></button>
                      ))}
                    </>
                  ) : null}
                </>
              ) : null}

              {!inNodeNetwork && selectorTab === "start" && startOperators.length > 0 ? (
                <>
                  <p className="px-4 pb-1 pt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">开始节点</p>
                  {renderCatalogItems(startOperators)}
                </>
              ) : null}

              {!inNodeNetwork && selectorTab === "snippets" && snippetOperators.length > 0 ? (
                <>
                  <p className="px-4 pb-1 pt-1 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">HDA 与可复用片段</p>
                  {renderCatalogItems(snippetOperators)}
                </>
              ) : null}

              {(inNodeNetwork || selectorTab === "blocks") && filteredOperators.length > 0 ? (
                <>
                  <p className="px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground/60">
                    注释与辅助
                  </p>
                  {filteredOperators.map((item) => {
                    const Icon = getIcon(item.icon)
                    return (
                      <button
                        key={`${item.nodeType}-${item.shape ?? item.label}`}
                        type="button"
                        onClick={() => addOperator(item)}
                        className="flex w-full items-center gap-3 px-4 py-2 text-left transition-colors hover:bg-accent"
                      >
                        <Icon className="size-3.5 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate text-sm">{item.label}</span>
                        <span className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground/50">
                          {(item.shape ?? item.nodeType).toUpperCase()}
                        </span>
                      </button>
                    )
                  })}
                </>
              ) : null}

              {(inNodeNetwork
                ? primitiveOperators.length + filteredOperators.length === 0
                : !hasTopLevelResults) ? (
                <p className="px-4 py-6 text-center font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  没有匹配的{inNodeNetwork ? "组件" : SELECTOR_TABS.find(([key]) => key === selectorTab)?.[1]}
                </p>
              ) : null}
            </div>
          </>
        ) : (
          <div className="p-4">
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="size-4 text-[#ff7a17]" />
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#ff7a17]">
                AI 生成工作流
              </span>
            </div>
            <div className="relative">
              <textarea
                ref={aiRef}
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    void generate(aiPrompt)
                  }
                  if (e.key === "Escape") setAiMode(false)
                }}
                placeholder="描述你想要的流程，例如：用户下单后校验库存，成功则通知发货，失败则退款…"
                className="min-h-24 w-full resize-none rounded-md border bg-background p-3 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-[#ff7a17]/60 focus:outline-none"
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => void generate(aiPrompt)}
                disabled={loading || !aiPrompt.trim()}
                className="absolute bottom-2.5 right-2.5 flex size-7 items-center justify-center rounded-sm bg-primary text-primary-foreground transition-opacity disabled:opacity-40"
                aria-label="生成"
              >
                {loading ? <Loader2 className="size-3.5 animate-spin" /> : <CornerDownLeft className="size-3.5" />}
              </button>
            </div>
            <div className="mt-3 space-y-1">
              {AI_EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  disabled={loading}
                  onClick={() => void generate(ex)}
                  className="block w-full truncate rounded-sm border border-transparent px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-border hover:text-foreground disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
            <p className="mt-3 font-mono text-[9px] uppercase tracking-wider text-muted-foreground/50">
              ⌘+Enter 生成 · ESC 返回
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
