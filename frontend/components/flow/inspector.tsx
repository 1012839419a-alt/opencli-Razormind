"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import {
  AlertTriangle,
  Database,
  ExternalLink,
  GitBranch,
  Plus,
  PlugZap,
  Trash2,
  Unplug,
} from "lucide-react"
import { useReactFlow } from "@xyflow/react"
import { clearParameterDraftEntry, useFlowStore } from "@/lib/flow/store"
import { portTypesCompatible, wouldCreateCycle } from "@/lib/flow/graph"
import { useSettingsStore } from "@/lib/flow/settings-store"
import { useSources } from "@/lib/api/hooks"
import type {
  FieldConfig,
  GeneratedWorkflowEdgeMapping,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeData,
} from "@/lib/flow/types"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { NodeInternalStatus } from "@/lib/workflow/node-internals"
import { getNodeTemplate } from "@/lib/workflow/node-templates"
import {
  buildParameterInterfaceView,
  parseJsonParameterValue,
  type ParameterInterfaceViewField,
} from "@/lib/workflow/parameter-interface"
import { blockedActionViewForRuntime } from "@/lib/workflow/capabilities"
import { businessNodeName } from "@/lib/workflow/business-node-experience"
import { buildCanonicalNodeViewContract } from "@/lib/workflow/canonical-node-contract"
import {
  getNodeDisplayId,
  localizeNodeParameterText,
  localizeNodeText,
  shouldPreserveNodeAuthoredText,
  type WorkflowLanguage,
} from "@/lib/workflow/node-i18n"
import { buildWorkflowOutlineRows } from "@/lib/workflow/workflow-outline"
import { findWorkflowProjectNodeByCanvasId } from "@/lib/workflow/node-path"
import {
  isOpenCLISourceSlotArray,
  type OpenCLISourceSlot,
} from "@/lib/workflow/node-catalog"
import {
  openCLISlotFromDataSource,
  SOURCE_ARGUMENT_LABELS,
  SOURCE_MARKET_OPTIONS,
  sourceBusinessArguments,
  sourceBusinessQuery,
  sourceMarket,
  sourceSlotKey,
  updateSourceBusinessQuery,
  updateSourceMarket,
} from "@/lib/workflow/source-business-config"
import type {
  WorkflowCapability,
  WorkflowNodeKind,
  WorkflowProject,
  WorkflowProjectNode,
} from "@/lib/workflow/schema"
import { MonoRow, PanelShell, SectionCaption } from "./inspector-shell"
import { cn } from "@/lib/utils"

const edgeTypeOptions = [
  { value: "workflow", label: "默认（贝塞尔曲线）" },
  { value: "editable", label: "可编辑路径" },
  { value: "routed", label: "智能避障（正交路由）" },
]

const edgeTypeHints: Record<string, string> = {
  workflow: "标准平滑曲线连线。",
  editable: "选中后可拖动控制点调整路径，双击线条添加控制点、双击控制点删除。",
  routed: "自动绕开中间节点的正交折线，适合密集流程图。",
}

const INSPECTOR_COPY = {
  "zh-CN": {
    switchLanguage: "切换节点语言",
    tabs: { outline: "大纲", config: "配置", run: "上次运行", trace: "Trace" },
    outlineHelp: "按真实连线生成流程大纲。单击选择并定位，双击或按 Enter 打开配置。",
    connectedFlow: "流程结构",
    needsAttention: "待连接节点",
    noNodes: "当前工作流还没有节点。",
    nodes: "节点",
    connections: "连线",
    promptSection: "节点提示词配置",
    promptHelp: "这里只显示节点已保存的提示词配置和测试用例。AI 编辑生成的是待审阅提案，确认应用后才会更新工作流。",
    configuredPrompt: "已配置提示词",
    testInput: "测试输入",
    expectedOutput: "期望输出",
    noPrompt: "当前节点未配置提示词测试用例。真实运行输入和输出只在执行时产生，请在“运行结果”或 Run Trace 中查看。",
    runResult: "运行结果",
    runHelp: "明确的运行结果会记录在 Run Trace 中；此处展示该节点的运行身份与产物摘要。",
    trace: "执行过程",
    traceHelp: "试运行后，可在 Run Trace 中按节点 ID 查看有序执行事件。",
    businessConfig: "业务配置",
    businessHelp: "名称和说明会直接显示在画布节点上。",
    systemNode: "系统能力",
    nodeName: "节点名称",
    nodeNamePlaceholder: "例如：采集 A 股市场数据",
    nodeDescription: "节点说明",
    nodeDescriptionPlaceholder: "说明这个节点为业务流程完成什么",
    blockedAction: "受阻动作",
    noPublicParameters: "此分组没有可配置参数。",
    contract: "运行契约",
    required: "必填",
    internals: "内部步骤",
    steps: "步",
    advanced: "高级设置",
    interface: "接口",
    inputs: "输入连接",
    inputsHelp: "每个输入端口只列出类型兼容的真实上游输出。可在这里重接或解绑。",
    inputUnbound: "未连接",
    noCompatibleOutputs: "没有可用的兼容输出。",
    fieldMapping: "字段映射",
    fieldMappingGap: "上下游契约尚未提供字段 schema，暂不允许手填来源或目标字段路径。已有旧映射只读保留。",
    legacyMapping: "旧映射",
    transform: "高级转换",
    compatibility: "兼容性",
    compilable: "可编译",
    blocked: "阻止发布 / 运行",
    noContract: "后端尚未为此节点投影输入/输出契约。",
    debug: "调试信息",
    dataSources: "数据来源",
    sourceHelp: "选择系统中已经连接的数据源，执行时自动并行采集。",
    manageSources: "管理数据源",
    sources: "个来源",
    parallel: "智能多源 · 并行执行",
    addConnectedSource: "添加已连接的数据源",
    loading: "加载中",
    addSource: "添加数据源",
    sourceUnavailable: "数据源目录暂时不可用。现有配置仍可使用，连接后端后即可选择其他来源。",
    noOtherSources: "全局目录中暂无其他已连接的 OpenCLI 数据源。",
    allSourcesAdded: "所有已连接的 OpenCLI 数据源都已添加到当前节点。",
    collectionTopic: "采集主题",
    collectionTopicPlaceholder: "例如：人工智能、贵州茅台",
    collectionTopicHint: "一次设置会同步到所有搜索型来源。",
    market: "市场范围",
    collectionOptions: "采集选项",
    items: "项",
    opencliMapping: "OpenCLI 映射",
    site: "站点",
    command: "命令",
    autoSaveHint: "配置会自动保存。使用画布顶部“试运行”检查真实返回和数据新鲜度。",
    parameters: "参数",
    jsonObjectRequired: "参数必须是 JSON 对象",
    invalidJson: "JSON 格式不正确",
    removeSource: "移除来源",
    sourceName: "名称",
  },
  "en-US": {
    switchLanguage: "Switch node language",
    tabs: { outline: "Outline", config: "Configure", run: "Last run", trace: "Trace" },
    outlineHelp: "Derived from real connections. Click to select and locate; double-click or press Enter to configure.",
    connectedFlow: "Flow",
    needsAttention: "Needs connection",
    noNodes: "This workflow has no nodes yet.",
    nodes: "nodes",
    connections: "connections",
    promptSection: "Node prompt configuration",
    promptHelp: "This shows only saved prompt configuration and test cases. AI edits remain review proposals until you apply them.",
    configuredPrompt: "Configured prompt",
    testInput: "Test input",
    expectedOutput: "Expected output",
    noPrompt: "This node has no prompt test case. Real inputs and outputs are created only during a run; inspect Run Result or Run Trace.",
    runResult: "Run result",
    runHelp: "Authoritative results live in Run Trace; this view summarizes the node identity and produced artifacts.",
    trace: "Execution trace",
    traceHelp: "After a test run, inspect ordered execution events by node ID in Run Trace.",
    businessConfig: "Business configuration",
    businessHelp: "The name and description appear directly on the canvas node.",
    systemNode: "System capability",
    nodeName: "Node name",
    nodeNamePlaceholder: "Example: Collect A-share market data",
    nodeDescription: "Node description",
    nodeDescriptionPlaceholder: "Explain what this node does for the business workflow",
    blockedAction: "Blocked action",
    noPublicParameters: "No configurable parameters in this group.",
    contract: "Runtime contract",
    required: "required",
    internals: "Internal steps",
    steps: "steps",
    advanced: "Advanced",
    interface: "Interface",
    inputs: "Inputs",
    inputsHelp: "Each input lists only type-compatible outputs from real upstream nodes. Reconnect or unbind here.",
    inputUnbound: "Unbound",
    noCompatibleOutputs: "No compatible outputs are available.",
    fieldMapping: "Field mapping",
    fieldMappingGap: "The upstream and downstream contracts do not expose field schemas yet. Manual source and target field paths are disabled; legacy mappings remain read-only.",
    legacyMapping: "Legacy mapping",
    transform: "Advanced transform",
    compatibility: "Compatibility",
    compilable: "Compilable",
    blocked: "Blocks publish / run",
    noContract: "No backend input/output contract is projected for this node.",
    debug: "Debug",
    dataSources: "Data sources",
    sourceHelp: "Choose connected data sources; the node collects from them in parallel at runtime.",
    manageSources: "Manage sources",
    sources: "sources",
    parallel: "Smart multi-source · parallel execution",
    addConnectedSource: "Add a connected data source",
    loading: "Loading",
    addSource: "Add source",
    sourceUnavailable: "The data source catalog is temporarily unavailable. Existing configuration remains usable.",
    noOtherSources: "No other connected OpenCLI data sources are available in the global catalog.",
    allSourcesAdded: "All connected OpenCLI data sources are already added to this node.",
    collectionTopic: "Collection topic",
    collectionTopicPlaceholder: "Example: artificial intelligence, Apple",
    collectionTopicHint: "One value is synchronized to every search-based source.",
    market: "Market scope",
    collectionOptions: "Collection options",
    items: "items",
    opencliMapping: "OpenCLI mapping",
    site: "Site",
    command: "Command",
    autoSaveHint: "Configuration saves automatically. Use Test Run to verify live results and data freshness.",
    parameters: "Parameters",
    jsonObjectRequired: "Parameters must be a JSON object",
    invalidJson: "Invalid JSON",
    removeSource: "Remove source",
    sourceName: "Name",
  },
} as const

const PARAMETER_GROUP_TEXT: Record<string, Record<WorkflowLanguage, string>> = {
  "Parameter Interface": { "zh-CN": "参数配置", "en-US": "Parameters" },
  Configuration: { "zh-CN": "配置", "en-US": "Configuration" },
  Internals: { "zh-CN": "内部参数", "en-US": "Internals" },
  Advanced: { "zh-CN": "高级参数", "en-US": "Advanced" },
  Input: { "zh-CN": "输入", "en-US": "Input" },
  Output: { "zh-CN": "输出", "en-US": "Output" },
}

const internalStatusLabel: Record<NodeInternalStatus, string> = {
  ready: "READY",
  simulated: "SIM",
  future: "NEXT",
}

const internalStatusClass: Record<NodeInternalStatus, string> = {
  ready: "border-[#4ade80]/30 bg-[#4ade80]/10 text-[#4ade80]",
  simulated: "border-[#a0c3ec]/30 bg-[#a0c3ec]/10 text-[#a0c3ec]",
  future: "border-border bg-muted text-muted-foreground",
}

const houdiniInputClass =
  "h-7 rounded-[2px] border-[#2c3036] bg-[#07080a] px-2 font-mono text-[11px] text-foreground shadow-inner outline-none transition-colors placeholder:text-muted-foreground/45 focus-visible:border-[#5f6976] focus-visible:ring-0 focus-visible:ring-offset-0 disabled:opacity-60 read-only:opacity-80"

const houdiniSelectTriggerClass =
  "h-7 rounded-[2px] border-[#2c3036] bg-[#07080a] px-2 font-mono text-[11px] shadow-inner focus:ring-0 focus:ring-offset-0"

const houdiniTextareaClass =
  "min-h-20 rounded-[2px] border-[#2c3036] bg-[#07080a] px-2 py-1.5 font-mono text-[11px] leading-relaxed shadow-inner focus-visible:ring-0 focus-visible:ring-offset-0"

const houdiniDetailsClass = "overflow-hidden rounded-[3px] border border-[#20242a] bg-[#111317]/74"

const houdiniSummaryClass =
  "flex cursor-pointer list-none items-center justify-between gap-3 bg-[#171a1f] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition-colors hover:text-foreground"

type InspectorMode = keyof typeof INSPECTOR_COPY["zh-CN"]["tabs"]

function InspectorLanguageToggle({
  language,
  onChange,
}: {
  language: WorkflowLanguage
  onChange: (language: WorkflowLanguage) => void
}) {
  const copy = INSPECTOR_COPY[language]
  return (
    <div className="flex items-center justify-end">
      <div className="flex items-center rounded-xs border bg-background p-0.5" role="group" aria-label={copy.switchLanguage}>
        {(["zh-CN", "en-US"] as const).map((candidate) => (
          <button
            key={candidate}
            type="button"
            aria-pressed={language === candidate}
            onClick={() => onChange(candidate)}
            className={cn(
              "min-h-7 rounded-xs px-2 font-mono text-2xs transition-colors",
              language === candidate
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {candidate === "zh-CN" ? "中" : "EN"}
          </button>
        ))}
      </div>
    </div>
  )
}

function InspectorModeTabs({
  active,
  copy,
  hasSelection,
  onChange,
}: {
  active: InspectorMode
  copy: typeof INSPECTOR_COPY[WorkflowLanguage]
  hasSelection: boolean
  onChange: (mode: InspectorMode) => void
}) {
  return (
    <div className="grid grid-cols-4 overflow-hidden rounded-[3px] border border-[#20242a] bg-[#171a1f] font-mono text-[10px] uppercase">
      {(["outline", "config", "run", "trace"] as const).map((mode) => {
        const disabled = mode !== "outline" && !hasSelection
        return (
          <button
            key={mode}
            type="button"
            disabled={disabled}
            onClick={() => onChange(mode)}
            className={cn(
              "border-r border-[#2b3037] px-2 py-2 transition-colors last:border-r-0",
              active === mode
                ? "bg-[#050607] text-foreground"
                : "text-muted-foreground hover:bg-[#252a31] hover:text-foreground",
              disabled && "cursor-not-allowed opacity-35",
            )}
          >
            {copy.tabs[mode]}
          </button>
        )
      })}
    </div>
  )
}

function WorkflowOutlinePanel({
  businessLevel,
  compact,
  edges,
  language,
  nodes,
  onClose,
  onLanguageChange,
  onModeChange,
  onOpenNode,
  onSelectNode,
  selectedNodeId,
  title,
  workflowProject,
}: {
  businessLevel: boolean
  compact: boolean
  edges: WorkflowEdge[]
  language: WorkflowLanguage
  nodes: WorkflowNode[]
  onClose: () => void
  onLanguageChange: (language: WorkflowLanguage) => void
  onModeChange: (mode: InspectorMode) => void
  onOpenNode: (nodeId: string) => void
  onSelectNode: (nodeId: string) => void
  selectedNodeId?: string
  title: string
  workflowProject: WorkflowProject
}) {
  const copy = INSPECTOR_COPY[language]
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const rows = buildWorkflowOutlineRows(nodes, edges)
  const connectedRows = rows.filter((row) => !row.disconnected)
  const disconnectedRows = rows.filter((row) => row.disconnected)
  const renderRows = (sectionRows: typeof rows) => (
    <div role="tree" className="overflow-hidden rounded-[3px] border border-[#20242a] bg-[#101216]/84">
      {sectionRows.map((row) => {
        const node = nodeById.get(row.nodeId)
        if (!node) return null
        const projectNode = findWorkflowProjectNodeByCanvasId(workflowProject, node.id)
        const configurationNode = findImplementationNode(projectNode) ?? projectNode
        const nodeViewContract = buildCanonicalNodeViewContract(projectNode, node.data, node.id)
        const systemText = localizeNodeText(
          getNodeDisplayId(node.data),
          { label: node.data.label, description: node.data.description },
          language,
        )
        const prefersCustomLabel =
          projectNode?.ui?.preferCustomLabel === true || shouldPreserveNodeAuthoredText(node.data)
        const localized = prefersCustomLabel
          ? { label: node.data.label, description: node.data.description }
          : systemText
        const displayLabel = businessLevel && !prefersCustomLabel
          ? businessNodeName({
              label: localized.label,
              kind: nodeViewContract.identity.kind as WorkflowNodeKind,
              capability: nodeViewContract.identity.capability as WorkflowCapability,
              params: configurationNode?.params ?? readCanonical(node.data)?.params,
              language,
            })
          : localized.label
        return (
          <button
            key={node.id}
            type="button"
            role="treeitem"
            aria-level={row.depth + 1}
            aria-selected={selectedNodeId === node.id}
            onClick={() => onSelectNode(node.id)}
            onDoubleClick={() => onOpenNode(node.id)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return
              event.preventDefault()
              onOpenNode(node.id)
            }}
            style={{ paddingLeft: 12 + row.depth * 16 }}
            className={cn(
              "flex w-full items-center gap-2 border-b border-[#20242a] py-2 pr-3 text-left transition-colors last:border-b-0 hover:bg-[#1b1f25]",
              selectedNodeId === node.id && "bg-[#20252c] text-foreground",
            )}
          >
            <span
              className={cn(
                "size-1.5 shrink-0 rounded-full",
                node.data.status === "error" ? "bg-destructive" : "bg-[#4ade80]",
              )}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11px] font-medium text-foreground">{displayLabel}</span>
              <span className="block truncate font-mono text-[9px] text-muted-foreground">
                {row.branchLabel ? `${row.branchLabel} · ` : ""}{node.data.nodeType}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )

  return (
    <PanelShell compact={compact} title={title} typeLine="WORKFLOW::OUTLINE · V1.0" onClose={onClose}>
      <div className="space-y-4 p-4">
        <InspectorLanguageToggle language={language} onChange={onLanguageChange} />
        <InspectorModeTabs
          active="outline"
          copy={copy}
          hasSelection={Boolean(selectedNodeId)}
          onChange={onModeChange}
        />
        <div className="rounded-[3px] border border-[#20242a] bg-[#101216]/84 p-3">
          <p className="text-[11px] leading-relaxed text-muted-foreground">{copy.outlineHelp}</p>
          <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/70">
            {nodes.length} {copy.nodes} · {edges.length} {copy.connections}
          </p>
        </div>
        {nodes.length === 0 ? (
          <p className="rounded-[3px] border border-dashed border-[#2a3038] p-4 text-[11px] text-muted-foreground">
            {copy.noNodes}
          </p>
        ) : null}
        {connectedRows.length > 0 ? (
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <GitBranch className="size-3 text-muted-foreground" />
              <SectionCaption>{copy.connectedFlow}</SectionCaption>
            </div>
            {renderRows(connectedRows)}
          </section>
        ) : null}
        {disconnectedRows.length > 0 ? (
          <section className="space-y-2">
            <div className="flex items-center gap-2">
              <Unplug className="size-3 text-[#f59e0b]" />
              <SectionCaption>{copy.needsAttention}</SectionCaption>
            </div>
            {renderRows(disconnectedRows)}
          </section>
        ) : null}
      </div>
    </PanelShell>
  )
}

type ProjectNodeWithIdentity = {
  params: Record<string, unknown>
  ui?: Record<string, unknown>
}

function hydrateProjectNodeIdentity<T extends ProjectNodeWithIdentity>(
  projectNode: T | undefined,
  data: WorkflowNodeData,
): T | undefined {
  const canonical = readCanonical(data)
  if (!projectNode || !canonical) return projectNode
  const catalogId = typeof projectNode.ui?.catalogId === "string" ? projectNode.ui.catalogId : canonical.catalogId
  const params = canonical.params ? { ...canonical.params, ...projectNode.params } : projectNode.params
  return {
    ...projectNode,
    params,
    ui: {
      ...projectNode.ui,
      ...(catalogId ? { catalogId } : {}),
    },
  }
}

type CanonicalNodeData = {
  catalogId?: string
  params?: Record<string, unknown>
}

function readCanonical(data: WorkflowNodeData): CanonicalNodeData | undefined {
  const canonical = data.canonical
  if (!canonical || typeof canonical !== "object" || Array.isArray(canonical)) return undefined
  return canonical as CanonicalNodeData
}

function nodeParameterDisplayValue(value: unknown): string | undefined {
  if (typeof value === "string") return value.trim() ? value : undefined
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return undefined
}

const UNBOUND_INPUT_VALUE = "__opencli_unbound__"

function inputBindingValue(nodeId: string, portId: string | null): string {
  return JSON.stringify([nodeId, portId])
}

function parseInputBindingValue(value: string): { nodeId: string; portId: string | null } | undefined {
  try {
    const parsed: unknown = JSON.parse(value)
    if (!Array.isArray(parsed) || typeof parsed[0] !== "string") return undefined
    if (parsed[1] !== null && typeof parsed[1] !== "string") return undefined
    return { nodeId: parsed[0], portId: parsed[1] }
  } catch {
    return undefined
  }
}

export function Inspector({ compact = false, onClose }: { compact?: boolean; onClose: () => void }) {
  const nodes = useFlowStore((s) => s.nodes)
  const edges = useFlowStore((s) => s.edges)
  const workflowProject = useFlowStore((s) => s.workflowProject)
  const networkStackLength = useFlowStore((s) => s.networkStack.length)
  const updateNodeData = useFlowStore((s) => s.updateNodeData)
  const updateEdgeData = useFlowStore((s) => s.updateEdgeData)
  const updateEdgeType = useFlowStore((s) => s.updateEdgeType)
  const toggleEdgeAnimated = useFlowStore((s) => s.toggleEdgeAnimated)
  const updateWorkflowNodeParams = useFlowStore((s) => s.updateWorkflowNodeParams)
  const updateParameterInterfaceField = useFlowStore((s) => s.updateParameterInterfaceField)
  const connectNodes = useFlowStore((s) => s.connectNodes)
  const onReconnect = useFlowStore((s) => s.onReconnect)
  const removeEdgesByIds = useFlowStore((s) => s.removeEdgesByIds)
  const takeSnapshot = useFlowStore((s) => s.takeSnapshot)
  const setNodes = useFlowStore((s) => s.setNodes)
  const onEdgesChange = useFlowStore((s) => s.onEdgesChange)
  const [nodeTab, setNodeTab] = useState<InspectorMode>("outline")
  const [parameterGroupTab, setParameterGroupTab] = useState("")
  const [jsonDrafts, setJsonDrafts] = useState<Record<string, string>>({})
  const [jsonErrors, setJsonErrors] = useState<Record<string, string>>({})
  const [pinnedNodeId, setPinnedNodeId] = useState<string>()
  const language = useSettingsStore((state) => state.language)
  const setLanguage = useSettingsStore((state) => state.set)
  const copy = INSPECTOR_COPY[language]
  const { getInternalNode, setCenter } = useReactFlow<WorkflowNode, WorkflowEdge>()

  const canvasSelected = nodes.filter((n) => n.selected)
  const pinnedNode = pinnedNodeId ? nodes.find((node) => node.id === pinnedNodeId) : undefined
  const selected = pinnedNode ? [pinnedNode] : canvasSelected
  const selectedEdges = edges.filter((e) => e.selected)
  const selectedNodeId = selected.length === 1 ? selected[0].id : undefined

  useEffect(() => {
    if (pinnedNodeId && !pinnedNode) setPinnedNodeId(undefined)
  }, [pinnedNode, pinnedNodeId])

  const locateOutlineNode = (nodeId: string) => {
    const outlineNode = nodes.find((candidate) => candidate.id === nodeId)
    if (!outlineNode) return
    const internalNode = getInternalNode(nodeId)
    const position = internalNode?.internals.positionAbsolute ?? outlineNode.position
    const width = internalNode?.measured.width ?? outlineNode.measured?.width ?? 0
    const height = internalNode?.measured.height ?? outlineNode.measured?.height ?? 0
    void setCenter(position.x + width / 2, position.y + height / 2, { zoom: 1, duration: 300 })
  }
  const selectOutlineNode = (nodeId: string) => {
    if (pinnedNodeId) setPinnedNodeId(nodeId)
    setNodes((current) => current.map((candidate) => ({
      ...candidate,
      selected: candidate.id === nodeId,
    })))
    onEdgesChange(
      edges
        .filter((edge) => edge.selected)
        .map((edge) => ({ id: edge.id, type: "select" as const, selected: false })),
    )
    locateOutlineNode(nodeId)
  }

  /* ---- edge parameter interface ---- */
  if (selected.length === 0 && selectedEdges.length === 1) {
    const edge = selectedEdges[0]
    const edgeType = edge.type ?? "workflow"
    const mapping: GeneratedWorkflowEdgeMapping = edge.data?.mapping ?? {
      mode: "auto",
      fields: [],
      preserveRaw: true,
      compatible: true,
      conflicts: [],
    }
    const updateMapping = (patch: Partial<GeneratedWorkflowEdgeMapping>) => {
      updateEdgeData(edge.id, {
        mapping: {
          ...mapping,
          ...patch,
          preserveRaw: true,
        },
      })
    }
    const updateMappingTransform = (
      index: number,
      transform: string | undefined,
    ) => {
      updateMapping({
        fields: mapping.fields.map((field, fieldIndex) =>
          fieldIndex === index ? { ...field, transform } : field,
        ),
      })
    }
    return (
      <PanelShell
        compact={compact}
        title="Connection"
        typeLine={`EDGE::${edgeType.toUpperCase()}`}
        onClose={onClose}
      >
        <div className="space-y-4 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="edge-label" className="font-mono text-[10px] uppercase tracking-wider">
              Label
            </Label>
            <Input
              id="edge-label"
              value={(edge.data?.label as string) ?? ""}
              onFocus={takeSnapshot}
              onChange={(e) => updateEdgeData(edge.id, { label: e.target.value })}
              placeholder="例如：成功 / 失败"
            />
          </div>

          <div className="space-y-3 rounded-md border bg-card p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <SectionCaption>{copy.fieldMapping}</SectionCaption>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  {copy.fieldMappingGap}
                </p>
              </div>
              <span className="shrink-0 rounded-xs border border-ops-line bg-ops-raised px-2 py-1 font-mono text-3xs uppercase text-zinc-400">
                {mapping.mode}
              </span>
            </div>

            {mapping.fields.map((field, index) => (
              <div key={index} className="space-y-2 rounded-md border bg-background p-2">
                <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 font-mono text-2xs">
                  <span className="truncate rounded-xs border border-ops-line bg-ops-raised px-2 py-1.5 text-zinc-300" title={field.source}>
                    {field.source}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">→</span>
                  <span className="truncate rounded-xs border border-ops-line bg-ops-raised px-2 py-1.5 text-zinc-300" title={field.target}>
                    {field.target}
                  </span>
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`edge-transform-${index}`} className="font-mono text-3xs uppercase tracking-wider text-zinc-500">
                    {copy.transform}
                  </Label>
                  <Input
                    id={`edge-transform-${index}`}
                    aria-label={`映射 ${index + 1} 转换`}
                    value={field.transform ?? ""}
                    onFocus={takeSnapshot}
                    onChange={(event) => updateMappingTransform(index, event.target.value || undefined)}
                    placeholder={language === "zh-CN" ? "可选转换表达式" : "Optional transform expression"}
                    className={houdiniInputClass}
                  />
                </div>
              </div>
            ))}

            {mapping.fields.length === 0 ? (
              <p className="rounded-xs border border-dashed border-ops-line p-3 text-2xs leading-relaxed text-zinc-500">
                {copy.fieldMappingGap}
              </p>
            ) : (
              <p className="font-mono text-3xs uppercase tracking-wider text-zinc-500">
                {copy.legacyMapping} · {mapping.fields.length}
              </p>
            )}

            <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
              <span className="text-muted-foreground">{copy.compatibility}</span>
              <span className={mapping.compatible ? "text-success" : "text-destructive"}>
                {mapping.compatible ? copy.compilable : copy.blocked}
              </span>
            </div>
            {mapping.conflicts.map((conflict) => (
              <p key={conflict} className="text-[11px] leading-relaxed text-destructive">
                {conflict}
              </p>
            ))}
          </div>

          <div className="space-y-1.5">
            <Label className="font-mono text-[10px] uppercase tracking-wider">Type</Label>
            <Select value={edgeType} onValueChange={(v) => v && updateEdgeType(edge.id, v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {edgeTypeOptions.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] leading-relaxed text-muted-foreground">{edgeTypeHints[edgeType]}</p>
          </div>

          <Separator />

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="edge-anim" className="font-mono text-[10px] uppercase tracking-wider">
                Flow Animation
              </Label>
              <p className="text-[11px] text-muted-foreground">显示流向的虚线动画</p>
            </div>
            <input
              id="edge-anim"
              type="checkbox"
              checked={!!edge.animated}
              onChange={() => toggleEdgeAnimated(edge.id)}
              className="houdini-checkbox"
            />
          </div>

          <Separator />
          <div className="space-y-1.5 rounded-md border bg-card p-3">
            <SectionCaption>Debug</SectionCaption>
            <MonoRow k="id" v={edge.id} />
            <MonoRow k="wire" v={`${edge.source} → ${edge.target}`} />
          </div>
        </div>
      </PanelShell>
    )
  }

  if (selected.length !== 1 || nodeTab === "outline") {
    return (
      <WorkflowOutlinePanel
        businessLevel={networkStackLength === 0}
        compact={compact}
        edges={edges}
        language={language}
        nodes={nodes}
        onClose={onClose}
        onLanguageChange={(nextLanguage) => setLanguage("language", nextLanguage)}
        onModeChange={setNodeTab}
        onOpenNode={(nodeId) => {
          selectOutlineNode(nodeId)
          setNodeTab("config")
        }}
        onSelectNode={selectOutlineNode}
        selectedNodeId={selectedNodeId}
        title={workflowProject.name}
        workflowProject={workflowProject}
      />
    )
  }

  /* ---- node parameter interface ---- */
  const node = selected[0]
  const data = node.data as WorkflowNodeData
  const canonical = data.canonical as { kind?: string; capability?: string; adapter?: string; params?: Record<string, unknown> } | undefined
  const projectNode = hydrateProjectNodeIdentity(
    findWorkflowProjectNodeByCanvasId(workflowProject, node.id),
    data,
  )
  const implementationNode = findImplementationNode(projectNode)
  const configurationNode = implementationNode ?? projectNode
  const configurationNodeId = implementationNode
    ? `${node.id}__${implementationNode.id}`
    : node.id
  const projectAdapter = configurationNode?.adapter
    ? workflowProject.adapters.find((candidate) => candidate.id === configurationNode.adapter)
    : undefined
  const nodeTemplate = getNodeTemplate(configurationNode)
  const nodeViewContract = buildCanonicalNodeViewContract(projectNode, data, node.id)
  const isBusinessLevel = networkStackLength === 0
  const localizedSystemText = localizeNodeText(
    getNodeDisplayId(data),
    { label: data.label, description: data.description },
    language,
  )
  const prefersCustomLabel =
    projectNode?.ui?.preferCustomLabel === true || shouldPreserveNodeAuthoredText(data)
  const localizedNodeText = prefersCustomLabel
    ? { label: data.label, description: data.description }
    : localizedSystemText
  const businessLabel = prefersCustomLabel
    ? localizedNodeText.label
    : businessNodeName({
        label: localizedNodeText.label,
        kind: nodeViewContract.identity.kind as WorkflowNodeKind,
        capability: nodeViewContract.identity.capability as WorkflowCapability,
        params: configurationNode?.params ?? canonical?.params,
        language,
      })
  const parameterInterfaceView = buildParameterInterfaceView({
    node: configurationNode,
    adapter: projectAdapter,
    nodes,
    allowedParamIds: implementationNode
      ? undefined
      : nodeViewContract.params.map((param) => param.id),
    runtimeCapability: data.runtimeCapability,
  })
  const nodeInternals = nodeViewContract.internals
  const nodeContract = nodeViewContract.staticContract
  const promptCapable =
    canonical?.kind === "agent" ||
    typeof data.primitiveId === "string" && (data.primitiveId.includes("prompt") || data.primitiveId.includes("model"))
  const promptParameter = (id: string) =>
    projectNode?.params[id] ?? canonical?.params?.[id] ?? data.fields?.find((field) => field.id === id)?.value
  const promptConfiguration: Array<{ key: string; value: string }> = [
    { key: "preset", value: promptParameter("style") },
    { key: "version", value: promptParameter("promptVersion") ?? promptParameter("version") },
    { key: "model", value: promptParameter("model") },
  ].flatMap(({ key, value }) => {
    const displayValue = nodeParameterDisplayValue(value)
    return displayValue ? [{ key, value: displayValue }] : []
  })
  const configuredPrompt = nodeParameterDisplayValue(promptParameter("prompt") ?? promptParameter("systemPrompt"))
  const testInput = nodeParameterDisplayValue(promptParameter("input"))
  const expectedOutput = nodeParameterDisplayValue(promptParameter("expected"))

  const update = (patch: Partial<WorkflowNodeData>) => updateNodeData(node.id, patch)

  const updateField = (fieldId: string, value: string) => {
    const fields = (data.fields ?? []).map((f: FieldConfig) =>
      f.id === fieldId ? { ...f, value } : f,
    )
    update({ fields })
  }

  const updateParameterField = (field: ParameterInterfaceViewField, value: unknown) => {
    if (field.readonly) return
    if (field.binding.source === "params" && field.binding.fieldId === "operatorId") {
      const configFields = parameterInterfaceView?.fields.filter(
        (candidate) => candidate.binding.source === "params" && candidate.binding.fieldId.startsWith("config."),
      ) ?? []
      for (const configField of configFields) {
        setJsonDrafts((drafts) => clearParameterDraftEntry(drafts, configurationNodeId, configField.id))
        setJsonErrors((errors) => clearParameterDraftEntry(errors, configurationNodeId, configField.id))
      }
    }
    if (parameterInterfaceView?.mode === "template") {
      if (field.binding.source === "adapter") {
        if (field.binding.fieldId === "mode") {
          updateWorkflowNodeParams(configurationNodeId, {}, { mode: value as never })
          return
        }
        updateWorkflowNodeParams(configurationNodeId, {}, { config: { [field.binding.fieldId]: value } })
        return
      }
      if (field.binding.source === "data") {
        update({ [field.binding.fieldId]: value } as Partial<WorkflowNodeData>)
        return
      }
      updateWorkflowNodeParams(configurationNodeId, { [field.binding.fieldId]: value })
      return
    }
    updateParameterInterfaceField(configurationNodeId, field.id, value)
  }

  const renderParameterField = (field: ParameterInterfaceViewField) => {
    const raw = field.value
    const fieldId = `parameter-${field.id}`
    const fieldText = localizeNodeParameterText(
      field.binding.fieldId,
      { label: field.label, description: field.description },
      language,
    )
    const label = (
      <div className="min-w-0 pt-1 text-right">
        <Label
          htmlFor={fieldId}
          title={fieldText.description}
          className="block truncate font-mono text-[10px] uppercase tracking-[0.04em] text-muted-foreground"
        >
          {fieldText.label}
        </Label>
      </div>
    )
    const readonlyTone = field.readonly ? "opacity-70" : ""
    const row = (control: React.ReactNode, align = "items-start") => (
      <div
        key={field.id}
        className={cn(
          "grid grid-cols-[118px_minmax(0,1fr)] gap-3 border-b border-[#24282f] px-1 py-2 last:border-b-0",
          align,
          readonlyTone,
        )}
      >
        {label}
        <div className="min-w-0">{control}</div>
      </div>
    )

    if (field.type === "json") {
      const draftKey = `${configurationNodeId}:${field.id}`
      const value = jsonDrafts[draftKey] ?? formatJsonParameterValue(raw)
      const error = jsonErrors[draftKey]
      return row(
        <div className="space-y-1">
          <Textarea
            id={fieldId}
            rows={5}
            readOnly={field.readonly}
            className={cn(houdiniTextareaClass, error && "border-[#f87171]/70")}
            value={value}
            onChange={(event) => {
              const next = event.target.value
              setJsonDrafts((drafts) => ({ ...drafts, [draftKey]: next }))
              const parsed = parseJsonParameterValue(next)
              if (!parsed.ok) {
                setJsonErrors((errors) => ({ ...errors, [draftKey]: parsed.error }))
                return
              }
              setJsonErrors((errors) => {
                const updated = { ...errors }
                delete updated[draftKey]
                return updated
              })
              updateParameterField(field, parsed.value)
            }}
            onBlur={() => {
              if (jsonErrors[draftKey]) return
              setJsonDrafts((drafts) => {
                const updated = { ...drafts }
                delete updated[draftKey]
                return updated
              })
            }}
          />
          {error ? <p role="alert" className="font-mono text-[10px] text-[#f87171]">{error}</p> : null}
        </div>,
      )
    }

    if (field.type === "boolean") {
      const checked = raw === true || raw === "true"
      return row(
        <div className="flex h-7 items-center">
          <input
            id={fieldId}
            type="checkbox"
            checked={checked}
            disabled={field.readonly}
            onChange={(event) => updateParameterField(field, event.target.checked)}
            className="houdini-checkbox"
          />
        </div>,
        "items-center",
      )
    }

    if (field.type === "select") {
      const value = typeof raw === "string" ? raw : field.options?.[0]?.value
      const selectedLabel = field.options?.find((option) => option.value === value)?.label ?? value ?? ""
      return row(
        field.readonly ? (
          <Input
            id={fieldId}
            readOnly
            value={selectedLabel}
            className={houdiniInputClass}
          />
        ) : (
          <Select value={value} onValueChange={(next) => updateParameterField(field, next)}>
            <SelectTrigger id={fieldId} className={houdiniSelectTriggerClass}>
              <span className="min-w-0 flex-1 truncate text-left">{selectedLabel}</span>
            </SelectTrigger>
            <SelectContent className="rounded-[2px] border border-[#2c3036] bg-[#0d0f12] font-mono text-[11px]">
              {(field.options ?? []).map((option) => (
                <SelectItem key={option.value} value={option.value} className="rounded-[2px] text-[11px]">
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ),
      )
    }

    if (field.type === "textarea") {
      return row(
          <Textarea
            id={fieldId}
            rows={3}
            readOnly={field.readonly}
            className={houdiniTextareaClass}
            value={typeof raw === "string" ? raw : ""}
            onChange={(e) => updateParameterField(field, e.target.value)}
          />,
      )
    }

    if (field.type === "tokens") {
      const selectedValues = new Set(
        Array.isArray(raw)
          ? raw.filter((value): value is string => typeof value === "string")
          : typeof raw === "string" && raw
            ? raw.split(",").map((value) => value.trim()).filter(Boolean)
            : [],
      )
      const options = field.options ?? []
      const optionValues = new Set(options.map((option) => option.value))
      const visibleOptions = [
        ...options,
        ...Array.from(selectedValues)
          .filter((value) => !optionValues.has(value))
          .map((value) => ({ value, label: value })),
      ]
      return row(
        <div className="flex flex-wrap items-center gap-1">
          {visibleOptions.map((option) => {
            const selectedToken = selectedValues.has(option.value)
            return (
              <button
                key={option.value}
                type="button"
                disabled={field.readonly}
                onClick={() => {
                  const next = new Set(selectedValues)
                  if (next.has(option.value)) next.delete(option.value)
                  else next.add(option.value)
                  updateParameterField(field, Array.from(next))
                }}
                className={cn(
                  "h-6 rounded-[2px] border px-2 font-mono text-[10px] transition-colors disabled:pointer-events-none disabled:opacity-60",
                  selectedToken
                    ? "border-[#8694a5] bg-[#2b3138] text-foreground"
                    : "border-[#2c3036] bg-[#07080a] text-muted-foreground hover:border-[#4a515c] hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            )
          })}
          {field.allowCustom ? (
            <Input
              disabled={field.readonly}
              placeholder="Add value"
              className={cn(houdiniInputClass, "h-6 w-28 px-2 text-[10px]")}
              onKeyDown={(event) => {
                if (event.key !== "Enter" && event.key !== ",") return
                event.preventDefault()
                const value = event.currentTarget.value.trim().replace(/,$/, "")
                if (!value) return
                updateParameterField(field, [...selectedValues, value])
                event.currentTarget.value = ""
              }}
            />
          ) : null}
        </div>,
      )
    }

    if (field.type === "slider") {
      const value = typeof raw === "number" ? raw : Number(raw ?? field.min ?? 0)
      const safeValue = Number.isFinite(value) ? value : field.min ?? 0
      return row(
        <div className="flex h-7 items-center gap-2">
          <div className="min-w-0 flex-1">
            <input
              id={fieldId}
              type="range"
              min={field.min ?? 0}
              max={field.max ?? 1}
              step={field.step ?? 0.01}
              value={safeValue}
              disabled={field.readonly}
              onChange={(e) => updateParameterField(field, Number(e.target.value))}
              className="houdini-range w-full disabled:opacity-60"
            />
          </div>
          <Input
            type="number"
            min={field.min ?? 0}
            max={field.max ?? 1}
            step={field.step ?? 0.01}
            value={safeValue}
            readOnly={field.readonly}
            onChange={(e) => updateParameterField(field, Number(e.target.value))}
            className={cn(houdiniInputClass, "h-7 w-[4.25rem] px-1.5 text-right")}
            aria-label={`${fieldText.label} numeric value`}
          />
        </div>,
        "items-center",
      )
    }

    if (field.type === "number") {
      const value =
        typeof raw === "number"
          ? raw
          : typeof raw === "string" && raw.trim()
            ? Number(raw)
            : undefined
      return row(
          <Input
            id={fieldId}
            type="number"
            min={field.min}
            max={field.max}
            step={field.step}
            readOnly={field.readonly}
            value={typeof value === "number" && Number.isFinite(value) ? value : field.optional ? "" : 0}
            onChange={(e) => {
              if (field.optional && !e.target.value) {
                updateParameterField(field, undefined)
                return
              }
              updateParameterField(field, Number(e.target.value))
            }}
            className={houdiniInputClass}
          />,
      )
    }

    return row(
        <Input
          id={fieldId}
          value={typeof raw === "string" || typeof raw === "number" ? String(raw) : ""}
          placeholder={field.placeholder}
          readOnly={field.readonly}
          onChange={(e) => updateParameterField(field, e.target.value)}
          className={houdiniInputClass}
        />,
    )
  }

  const isCondition = data.nodeType === "condition"
  const ports = nodeViewContract.ports.map((port) => ({
    name: port.id,
    dir: port.direction,
    type: port.type,
    description: port.description,
  }))
  const inputPorts = ports.filter((port) => port.dir === "input")
  const incomingEdgesForPort = (portName: string) => edges.filter((edge) =>
    edge.target === node.id &&
    (
      edge.targetHandle === portName ||
      (edge.targetHandle == null && inputPorts.length === 1)
    ),
  )
  const inputOptions = (targetPort: (typeof inputPorts)[number], currentEdge?: WorkflowEdge) =>
    nodes.flatMap((candidate) => {
      if (candidate.id === node.id) return []
      const candidateProjectNode = hydrateProjectNodeIdentity(
        findWorkflowProjectNodeByCanvasId(workflowProject, candidate.id),
        candidate.data,
      )
      const candidateContract = buildCanonicalNodeViewContract(
        candidateProjectNode,
        candidate.data,
        candidate.id,
      )
      const graphWithoutCurrent = currentEdge
        ? edges.filter((edge) => edge.id !== currentEdge.id)
        : edges
      if (wouldCreateCycle(graphWithoutCurrent, candidate.id, node.id)) return []
      const localized = localizeNodeText(
        getNodeDisplayId(candidate.data),
        { label: candidate.data.label, description: candidate.data.description },
        language,
      )
      return candidateContract.ports
        .filter((port) =>
          port.direction === "output" &&
          portTypesCompatible(port.type, targetPort.type),
        )
        .map((port) => ({
          value: inputBindingValue(candidate.id, port.id),
          label: `${localized.label} · ${port.id} (${port.type})`,
          nodeId: candidate.id,
          portId: port.id,
        }))
    })
  const parameterGroups = parameterInterfaceView?.groups ?? []
  const activeParameterGroupId = parameterGroups.some((group) => group.id === parameterGroupTab)
    ? parameterGroupTab
    : parameterGroups[0]?.id
  const activeParameterFields = parameterInterfaceView?.fields.filter((field) => field.groupId === activeParameterGroupId) ?? []
  const blockedAction = blockedActionViewForRuntime(data)
  const locateNode = () => {
    const internalNode = getInternalNode(node.id)
    const position = internalNode?.internals.positionAbsolute ?? node.position
    const width = internalNode?.measured.width ?? node.measured?.width ?? 0
    const height = internalNode?.measured.height ?? node.measured?.height ?? 0
    void setCenter(position.x + width / 2, position.y + height / 2, { zoom: 1, duration: 300 })
  }
  const openCLISources = isOpenCLISourceSlotArray(configurationNode?.params.sources)
    ? configurationNode.params.sources
    : undefined
  return (
    <PanelShell
      compact={compact}
      title={isBusinessLevel ? businessLabel : data.label}
      typeLine={`${nodeViewContract.identity.kind}::${nodeViewContract.identity.capability}`.toUpperCase() + " · V1.0"}
      status={data.status}
      onClose={onClose}
      onLocate={locateNode}
      pinned={pinnedNodeId === node.id}
      onTogglePin={() => setPinnedNodeId((current) => current === node.id ? undefined : node.id)}
    >
      <div className="space-y-4 p-4">
        <InspectorLanguageToggle
          language={language}
          onChange={(nextLanguage) => setLanguage("language", nextLanguage)}
        />
        <InspectorModeTabs
          active={nodeTab}
          copy={copy}
          hasSelection
          onChange={setNodeTab}
        />

        {nodeTab === "run" ? (
          <div className="space-y-3">
            <SectionCaption>{copy.runResult}</SectionCaption>
            <div className="rounded-md border bg-card p-3 text-[11px] leading-relaxed text-muted-foreground">
              {copy.runHelp}
            </div>
            <MonoRow k="node" v={node.id} />
            {canonical?.capability ? <MonoRow k="capability" v={canonical.capability} /> : null}
            {canonical?.adapter ? <MonoRow k="adapter" v={canonical.adapter} /> : null}
            <MonoRow k="artifacts" v={nodeViewContract.outputs.artifacts.join(", ") || "none"} />
            <MonoRow k="batches" v={nodeViewContract.outputs.evidenceBatchCount} />
          </div>
        ) : nodeTab === "trace" ? (
          <div className="space-y-3">
            <SectionCaption>{copy.trace}</SectionCaption>
            <div className="rounded-md border bg-card p-3 text-[11px] leading-relaxed text-muted-foreground">
              {copy.traceHelp}
            </div>
            <MonoRow k="profile" v={workflowProject.profile} />
            {canonical?.kind ? <MonoRow k="kind" v={canonical.kind} /> : null}
            <MonoRow k="events" v={nodeViewContract.trace.events.join(", ") || "none"} />
            {nodeViewContract.trace.runId ? <MonoRow k="run" v={nodeViewContract.trace.runId} /> : null}
            {nodeViewContract.trace.traceId ? <MonoRow k="trace" v={nodeViewContract.trace.traceId} /> : null}
          </div>
        ) : (
          <>
        <section className="space-y-3 rounded-[3px] border border-[#20242a] bg-[#101216]/84 p-3">
          <div>
            <SectionCaption>{copy.businessConfig}</SectionCaption>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {copy.businessHelp}
            </p>
            <p className="mt-1 font-mono text-3xs text-muted-foreground">
              {copy.systemNode}: {localizedSystemText.label}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="node-label" className="font-mono text-[10px] uppercase tracking-wider">
              {copy.nodeName}
            </Label>
            <Input
              id="node-label"
              value={data.label}
              onFocus={takeSnapshot}
              onChange={(event) => update({ label: event.target.value })}
              placeholder={copy.nodeNamePlaceholder}
              className={houdiniInputClass}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="node-desc" className="font-mono text-[10px] uppercase tracking-wider">
              {copy.nodeDescription}
            </Label>
            <Textarea
              id="node-desc"
              rows={2}
              value={data.description ?? ""}
              onFocus={takeSnapshot}
              onChange={(event) => update({ description: event.target.value })}
              placeholder={copy.nodeDescriptionPlaceholder}
              className={houdiniTextareaClass}
            />
          </div>
        </section>

        {promptCapable ? (
          <details className={houdiniDetailsClass}>
            <summary className={houdiniSummaryClass}>
              <span>{copy.promptSection}</span>
              <span className="truncate text-[10px] normal-case tracking-normal">
                {promptConfiguration.find((item) => item.key === "model")?.value ?? copy.systemNode}
              </span>
            </summary>
            <div className="space-y-3 border-t p-3">
              <p className="text-[11px] leading-relaxed text-muted-foreground">{copy.promptHelp}</p>
              {promptConfiguration.map(({ key, value }) => <MonoRow key={key} k={key} v={value} />)}
              {configuredPrompt ? (
                <div className="space-y-1.5">
                  <Label className="font-mono text-[10px] uppercase tracking-wider">{copy.configuredPrompt}</Label>
                  <Textarea readOnly rows={4} className="font-mono text-xs" value={configuredPrompt} />
                </div>
              ) : null}
              {testInput || expectedOutput ? <Separator /> : null}
              {testInput ? (
                <div className="space-y-1.5">
                  <Label className="font-mono text-[10px] uppercase tracking-wider">{copy.testInput}</Label>
                  <Textarea readOnly rows={3} className="font-mono text-xs" value={testInput} />
                </div>
              ) : null}
              {expectedOutput ? (
                <div className="space-y-1.5">
                  <Label className="font-mono text-[10px] uppercase tracking-wider">{copy.expectedOutput}</Label>
                  <Textarea readOnly rows={4} className="font-mono text-xs" value={expectedOutput} />
                </div>
              ) : null}
              {!configuredPrompt && !testInput && !expectedOutput ? (
                <p className="rounded-md border border-dashed bg-card p-3 text-[11px] leading-relaxed text-muted-foreground">
                  {copy.noPrompt}
                </p>
              ) : null}
            </div>
          </details>
        ) : null}

        {blockedAction ? (
          <div className="overflow-hidden rounded-[3px] border border-[#7f1d1d]/60 bg-[#180b0b]/70">
            <div className="flex items-center justify-between gap-3 border-b border-[#7f1d1d]/50 bg-[#2a1010]/72 px-3 py-2">
              <div className="flex min-w-0 items-center gap-2">
                <AlertTriangle className="size-3.5 shrink-0 text-[#f87171]" />
                <SectionCaption>{copy.blockedAction}</SectionCaption>
              </div>
              <Link
                href={blockedAction.href}
                className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[2px] border border-[#f87171]/35 bg-[#3a1515] px-2 font-mono text-[10px] uppercase tracking-[0.06em] text-[#fecaca] transition-colors hover:border-[#fecaca]/50 hover:bg-[#4a1717]"
              >
                <PlugZap className="size-3" />
                <span>{blockedAction.actionLabel}</span>
              </Link>
            </div>
            <div className="space-y-2 p-3">
              <p className="line-clamp-2 text-[11px] leading-relaxed text-[#fecaca]/85">{blockedAction.message}</p>
              {blockedAction.missingLabels.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {blockedAction.missingLabels.map((label) => (
                    <span
                      key={label}
                      className="rounded-[2px] border border-[#7f1d1d]/60 bg-[#120707] px-2 py-1 font-mono text-[10px] text-[#fecaca]/75"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {openCLISources ? (
          <OpenCLISourceEditor
            sources={openCLISources}
            language={language}
            onChange={(sources) => updateWorkflowNodeParams(configurationNodeId, { sources })}
          />
        ) : null}

        <details className={houdiniDetailsClass} open>
          <summary className={houdiniSummaryClass}>
            <span>{copy.inputs}</span>
            <span className="text-3xs normal-case tracking-normal">{inputPorts.length} IN</span>
          </summary>
          <div className="space-y-3 border-t border-ops-line p-3">
            <p className="text-2xs leading-relaxed text-zinc-500">{copy.inputsHelp}</p>
            {inputPorts.map((port) => {
              const currentEdges = incomingEdgesForPort(port.name)
              const currentEdge = currentEdges[0]
              const options = inputOptions(port, currentEdge)
              const currentOption = currentEdge
                ? options.find((option) =>
                    option.nodeId === currentEdge.source &&
                    (
                      option.portId === currentEdge.sourceHandle ||
                      currentEdge.sourceHandle == null
                    ),
                  )
                : undefined
              const legacyValue = currentEdge ? `__opencli_legacy__${currentEdge.id}` : undefined
              const currentValue = currentOption?.value ?? legacyValue ?? UNBOUND_INPUT_VALUE
              return (
                <div key={port.name} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <Label className="truncate font-mono text-2xs text-zinc-200">{port.name}</Label>
                    <span className="shrink-0 font-mono text-3xs uppercase text-zinc-500">{port.type}</span>
                  </div>
                  <Select
                    value={currentValue}
                    onValueChange={(value) => {
                      if (!value) return
                      if (value === UNBOUND_INPUT_VALUE) {
                        if (currentEdges.length > 0) removeEdgesByIds(currentEdges.map((edge) => edge.id))
                        return
                      }
                      const binding = parseInputBindingValue(value)
                      if (!binding) return
                      const connection = {
                        source: binding.nodeId,
                        sourceHandle: binding.portId,
                        target: node.id,
                        targetHandle: port.name,
                      }
                      if (
                        currentEdge &&
                        currentEdge.source === connection.source &&
                        currentEdge.sourceHandle === connection.sourceHandle &&
                        currentEdge.targetHandle === connection.targetHandle
                      ) return
                      if (currentEdge) onReconnect(currentEdge, connection)
                      else connectNodes(connection)
                    }}
                  >
                    <SelectTrigger
                      aria-label={`${copy.inputs}: ${port.name}`}
                      className={houdiniSelectTriggerClass}
                    >
                      <SelectValue placeholder={copy.inputUnbound} />
                    </SelectTrigger>
                    <SelectContent className="rounded-xs border border-ops-line bg-ops-raised font-mono text-2xs">
                      <SelectItem value={UNBOUND_INPUT_VALUE}>{copy.inputUnbound}</SelectItem>
                      {currentEdge && !currentOption && legacyValue ? (
                        <SelectItem value={legacyValue} disabled>
                          {copy.legacyMapping} · {currentEdge.source}:{currentEdge.sourceHandle ?? "default"}
                        </SelectItem>
                      ) : null}
                      {options.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {options.length === 0 ? (
                    <p className="text-3xs text-zinc-500">{copy.noCompatibleOutputs}</p>
                  ) : null}
                  {currentEdge && !currentOption ? (
                    <p className="text-3xs leading-relaxed text-signal-warning">
                      {language === "zh-CN"
                        ? `当前旧连接 ${currentEdge.source}:${currentEdge.sourceHandle ?? "default"} 未被输入契约识别。`
                        : `The legacy connection ${currentEdge.source}:${currentEdge.sourceHandle ?? "default"} is not recognized by the input contract.`}
                    </p>
                  ) : null}
                </div>
              )
            })}
            {inputPorts.length === 0 ? (
              <p className="text-2xs leading-relaxed text-signal-danger">{copy.noContract}</p>
            ) : null}
          </div>
        </details>

        {parameterInterfaceView ? (
          <div className="overflow-hidden rounded-[3px] border border-[#20242a] bg-[#101216]/84">
            <div className="flex flex-wrap gap-0 border-b border-[#24282f] bg-[#1d2025] p-0 font-mono text-[10px] uppercase">
              {parameterGroups.map((group) => (
                <button
                  key={group.id}
                  type="button"
                  onClick={() => setParameterGroupTab(group.id)}
                  className={cn(
                    "border-r border-[#2b3037] px-3 py-1.5 transition-colors",
                    activeParameterGroupId === group.id
                      ? "bg-[#07080a] text-foreground"
                      : "text-muted-foreground hover:bg-[#252a31] hover:text-foreground",
                  )}
                >
                  {PARAMETER_GROUP_TEXT[group.label]?.[language] ?? group.label}
                </button>
              ))}
            </div>
            <div className="px-2 py-1">{activeParameterFields.map((field) => renderParameterField(field))}</div>
            {activeParameterFields.length === 0 ? (
              <p className="px-3 py-4 text-[11px] text-muted-foreground">{copy.noPublicParameters}</p>
            ) : null}
          </div>
        ) : null}

        {nodeContract || data.runtimeContract ? (
          <details className={houdiniDetailsClass}>
            <summary className={houdiniSummaryClass}>
              <span>{copy.contract}</span>
              <span className="truncate text-[10px] normal-case tracking-normal">
                {data.runtimeContract?.bindingId ?? nodeContract?.dataModel}
              </span>
            </summary>
            <div className="space-y-3 border-t p-3">
              <div className="space-y-1">
                <h3 className="text-xs font-medium text-foreground">{nodeContract?.title ?? nodeViewContract.identity.label}</h3>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {data.runtimeContract?.status ?? nodeContract?.dataModel}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <MonoRow k="ports" v={nodeViewContract.ports.length} />
                <MonoRow k="params" v={nodeViewContract.params.length} />
              </div>
              <Separator />
              <div className="space-y-1.5">
                {nodeViewContract.params.slice(0, 4).map((param) => (
                  <div key={param.id} className="flex items-center justify-between gap-2 font-mono text-[10px]">
                    <span className="truncate text-foreground">{param.id}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {param.type ?? "runtime"}{param.required ? ` · ${copy.required}` : ""}
                    </span>
                  </div>
                ))}
              </div>
              {nodeContract?.assertions.length ? (
                <>
                  <Separator />
                  <div className="space-y-1">
                    {nodeContract.assertions.slice(0, 3).map((assertion) => (
                      <p key={assertion} className="line-clamp-1 text-[11px] text-muted-foreground">
                        {assertion}
                      </p>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </details>
        ) : null}

        {nodeInternals ? (
          <details className={houdiniDetailsClass}>
            <summary className={houdiniSummaryClass}>
              <span>{copy.internals}</span>
              <span className="text-[10px] normal-case tracking-normal">{nodeInternals.steps.length} {copy.steps}</span>
            </summary>
            <div className="space-y-3 border-t p-3">
              <div className="space-y-1">
                <h3 className="text-xs font-medium text-foreground">{nodeInternals.title}</h3>
                <p className="text-[11px] leading-relaxed text-muted-foreground">{nodeInternals.summary}</p>
              </div>
              <div className="space-y-2">
                {nodeInternals.steps.map((step, index) => (
                  <div key={step.id} className="rounded-[3px] border border-[#252a31] bg-[#090a0c]/70 p-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <p className="truncate text-xs font-medium text-foreground">{step.label}</p>
                        </div>
                        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{step.description}</p>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[9px]",
                          internalStatusClass[step.status],
                        )}
                      >
                        {internalStatusLabel[step.status]}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-muted-foreground/80">
                      <span>{step.capability}</span>
                      <span className="truncate">{step.evidence}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </details>
        ) : null}

        {isCondition || (!nodeTemplate && data.fields && data.fields.length > 0) ? (
          <details className={houdiniDetailsClass}>
            <summary className={houdiniSummaryClass}>
              <span>{copy.advanced}</span>
              <span className="truncate text-[10px] normal-case tracking-normal">{data.label}</span>
            </summary>
            <div className="space-y-3 border-t p-3">
            {isCondition ? (
              <div className="space-y-1.5">
                <Label htmlFor="node-cond" className="font-mono text-[10px] uppercase tracking-wider">
                  Expression
                </Label>
                <Textarea
                  id="node-cond"
                  rows={2}
                  className={houdiniTextareaClass}
                  value={data.condition ?? ""}
                  onFocus={takeSnapshot}
                  onChange={(e) => update({ condition: e.target.value })}
                />
              </div>
            ) : null}

            {!nodeTemplate && data.fields && data.fields.length > 0
              ? data.fields.map((f: FieldConfig) => (
                  <div key={f.id} className="space-y-1.5">
                    <Label
                      htmlFor={`field-${f.id}`}
                      className="font-mono text-[10px] uppercase tracking-wider"
                    >
                      {f.label}
                    </Label>
                    <Input
                      id={`field-${f.id}`}
                      value={f.value}
                      onFocus={takeSnapshot}
                      onChange={(e) => updateField(f.id, e.target.value)}
                      className={houdiniInputClass}
                    />
                  </div>
                ))
              : null}
            </div>
          </details>
        ) : null}

        {data.nodeType !== "note" && data.nodeType !== "group" ? (
          <details className={houdiniDetailsClass}>
            <summary className={houdiniSummaryClass}>
              <span>{copy.interface}</span>
              <span className="text-[10px] normal-case tracking-normal">
                {ports.filter((port) => port.dir === "input").length} IN · {ports.filter((port) => port.dir === "output").length} OUT
              </span>
            </summary>
            <div className="space-y-1.5 border-t p-3">
              {ports.map((p) => (
                <div
                  key={`${p.dir}-${p.name}`}
                  className="flex items-center justify-between font-mono text-[11px]"
                >
                  <span className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        "size-1.5 rounded-[2px]",
                        p.dir === "input" ? "bg-[#a0c3ec]" : "bg-[#3a3d42]",
                      )}
                      aria-hidden
                    />
                    <span className="text-foreground">{p.name}</span>
                  </span>
                  <span className="text-muted-foreground/70">
                    {p.dir.toUpperCase()} · {p.type.toUpperCase()}
                  </span>
                </div>
              ))}
              {ports.length === 0 ? (
                <p className="text-[11px] leading-relaxed text-[#f87171]">
                  {copy.noContract}
                </p>
              ) : null}
            </div>
          </details>
        ) : null}

        <details className={houdiniDetailsClass}>
          <summary className={houdiniSummaryClass}>
            <span>{copy.debug}</span>
            <span className="truncate text-[10px] normal-case tracking-normal">{node.id}</span>
          </summary>
          <div className="space-y-1.5 border-t p-3">
            <MonoRow k="id" v={node.id} />
            <MonoRow k="pos" v={`${Math.round(node.position.x)}, ${Math.round(node.position.y)}`} />
            {node.parentId ? <MonoRow k="parent" v={node.parentId} /> : null}
          </div>
        </details>
          </>
        )}
      </div>
    </PanelShell>
  )
}

function findImplementationNode(node: WorkflowProjectNode | undefined): WorkflowProjectNode | undefined {
  if (!node) return undefined
  const operator = node.params.operator
  if (!operator || typeof operator !== "object" || Array.isArray(operator)) return undefined
  const implementationNodeId = (operator as Record<string, unknown>).implementationNodeId
  if (typeof implementationNodeId !== "string") return undefined
  return (node.internals?.nodes ?? []).find((candidate): candidate is WorkflowProjectNode => {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) return false
    return (candidate as { id?: unknown }).id === implementationNodeId
  })
}

function OpenCLISourceEditor({
  sources,
  language,
  onChange,
}: {
  sources: OpenCLISourceSlot[]
  language: WorkflowLanguage
  onChange: (sources: OpenCLISourceSlot[]) => void
}) {
  const copy = INSPECTOR_COPY[language]
  const sourceCatalog = useSources({ enabled: true, limit: 100 })
  const registeredSources = (sourceCatalog.data?.data ?? [])
    .map(openCLISlotFromDataSource)
    .filter((source): source is OpenCLISourceSlot => Boolean(source))
  const selectedSourceKeys = new Set(sources.map(sourceSlotKey))
  const availableSources = registeredSources.filter((source) => !selectedSourceKeys.has(sourceSlotKey(source)))
  const businessQuery = sourceBusinessQuery(sources)
  const market = sourceMarket(sources)

  const updateSource = (index: number, patch: Partial<OpenCLISourceSlot>) => {
    onChange(sources.map((source, sourceIndex) => (
      sourceIndex === index ? { ...source, ...patch } : source
    )))
  }

  const addSource = (sourceId: string | null) => {
    const source = availableSources.find((candidate) => candidate.id === sourceId)
    if (!source) return
    onChange([...sources, source])
  }

  return (
    <section className="overflow-hidden rounded-[3px] border border-[#20242a] bg-[#101216]/84">
      <div className="space-y-3 border-b border-[#24282f] bg-[#171a1f] p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <SectionCaption>{copy.dataSources}</SectionCaption>
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              {copy.sourceHelp}
            </p>
          </div>
          <Link
            href="/sources"
            className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[2px] border border-[#343a43] px-2 text-[10px] text-muted-foreground transition-colors hover:border-[#5f6976] hover:text-foreground"
          >
            {copy.manageSources}
            <ExternalLink className="size-3" />
          </Link>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-[3px] border border-[#2a2f36] bg-[#0b0d10] px-2.5 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-[2px] bg-[#ff7a17]/12 text-[#ff9a4a]">
              <Database className="size-3.5" />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-foreground">{sources.length} {copy.sources}</p>
              <p className="truncate text-[10px] text-muted-foreground">{copy.parallel}</p>
            </div>
          </div>
          <Select onValueChange={addSource} disabled={sourceCatalog.isLoading || availableSources.length === 0}>
            <SelectTrigger
              aria-label={copy.addConnectedSource}
              className="h-7 w-auto min-w-28 rounded-[2px] border-[#343a43] bg-[#111317] px-2 text-[11px] shadow-none focus:ring-0"
            >
              <Plus className="size-3" />
              <SelectValue placeholder={sourceCatalog.isLoading ? copy.loading : copy.addSource} />
            </SelectTrigger>
            <SelectContent>
              {availableSources.map((source) => (
                <SelectItem key={source.id} value={source.id}>
                  {source.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {sourceCatalog.isError ? (
          <p className="text-[10px] leading-relaxed text-[#fca5a5]">
            {copy.sourceUnavailable}
          </p>
        ) : !sourceCatalog.isLoading && registeredSources.length === 0 ? (
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            {language === "zh-CN" ? `当前节点已有 ${sources.length} 个来源；` : `This node has ${sources.length} sources; `}{copy.noOtherSources}
          </p>
        ) : !sourceCatalog.isLoading && availableSources.length === 0 ? (
          <p className="text-[10px] leading-relaxed text-muted-foreground">
            {copy.allSourcesAdded}
          </p>
        ) : null}
      </div>

      {businessQuery !== undefined || market !== undefined ? (
        <div className="grid gap-3 border-b border-[#24282f] bg-[#0d0f12] p-3">
          {businessQuery !== undefined ? (
            <div className="space-y-1.5">
              <Label htmlFor="source-business-query" className="text-[11px] font-medium text-foreground">
                {copy.collectionTopic}
              </Label>
              <Input
                id="source-business-query"
                value={businessQuery}
                onChange={(event) => onChange(updateSourceBusinessQuery(sources, event.target.value))}
                placeholder={copy.collectionTopicPlaceholder}
                className="h-8 rounded-[3px] border-[#303640] bg-[#080a0c] text-xs focus-visible:ring-0"
              />
              <p className="text-[10px] text-muted-foreground">{copy.collectionTopicHint}</p>
            </div>
          ) : null}
          {market !== undefined ? (
            <div className="space-y-1.5">
              <Label className="text-[11px] font-medium text-foreground">{copy.market}</Label>
              <Select value={market} onValueChange={(value) => value && onChange(updateSourceMarket(sources, value))}>
                <SelectTrigger className="h-8 rounded-[3px] border-[#303640] bg-[#080a0c] text-xs focus:ring-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {!SOURCE_MARKET_OPTIONS.some((option) => option.value === market) ? (
                    <SelectItem value={market}>{market}</SelectItem>
                  ) : null}
                  {SOURCE_MARKET_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2 p-2">
        {sources.map((source, index) => {
          const businessArguments = sourceBusinessArguments(source)
          return (
            <div key={source.id} className="rounded-[3px] border border-[#252a31] bg-[#090a0c]/70">
              <div className="flex items-center gap-2 p-2.5">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-[3px] border border-[#343a43] bg-[#15181d] font-mono text-[11px] font-semibold uppercase text-[#ff9a4a]">
                  {source.site.slice(0, 1)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-foreground">{source.label}</p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {source.site} · {source.sourceGroup || (language === "zh-CN" ? "数据采集" : "Data collection")}
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={`${copy.removeSource} ${source.label}`}
                  disabled={sources.length <= 1}
                  onClick={() => onChange(sources.filter((_, sourceIndex) => sourceIndex !== index))}
                  className="inline-flex size-7 shrink-0 items-center justify-center rounded-[2px] border border-[#2c3036] text-muted-foreground transition-colors hover:border-[#7f1d1d] hover:text-[#f87171] disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <Trash2 className="size-3" />
                </button>
              </div>
              {businessArguments.length > 0 ? (
                <details className="border-t border-[#20242a]">
                  <summary className="cursor-pointer list-none px-2.5 py-2 text-[10px] text-muted-foreground transition-colors hover:text-foreground">
                    {copy.collectionOptions} · {businessArguments.length} {copy.items}
                  </summary>
                  <div className="grid gap-2 border-t border-[#20242a] p-2.5">
                    {businessArguments.map(([key, value]) => (
                      <SourceBusinessArgument
                        key={key}
                        argumentKey={key}
                        value={value}
                        language={language}
                        onChange={(nextValue) => updateSource(index, { args: { ...source.args, [key]: nextValue } })}
                      />
                    ))}
                  </div>
                </details>
              ) : null}
            </div>
          )
        })}
      </div>

      <details className="border-t border-[#24282f] bg-[#111317]/74">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground">
          <span>{copy.advanced}</span>
          <span className="normal-case tracking-normal">{copy.opencliMapping}</span>
        </summary>
        <div className="space-y-2 border-t border-[#24282f] p-2">
          {sources.map((source, index) => (
            <div key={source.id} className="space-y-2 rounded-[3px] border border-[#252a31] bg-[#090a0c]/70 p-2.5">
              <Input
                aria-label={`${language === "zh-CN" ? "来源" : "Source"} ${index + 1} ${copy.sourceName}`}
                value={source.label}
                onChange={(event) => updateSource(index, { label: event.target.value })}
                className={houdiniInputClass}
              />
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">{copy.site}</Label>
                  <Input
                    aria-label={`${language === "zh-CN" ? "来源" : "Source"} ${index + 1} ${copy.site}`}
                    value={source.site}
                    onChange={(event) => updateSource(index, { site: event.target.value })}
                    className={houdiniInputClass}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">{copy.command}</Label>
                  <Input
                    aria-label={`${language === "zh-CN" ? "来源" : "Source"} ${index + 1} ${copy.command}`}
                    value={source.command}
                    onChange={(event) => updateSource(index, { command: event.target.value })}
                    className={houdiniInputClass}
                  />
                </div>
              </div>
              <SourceArgsEditor
                sourceId={source.id}
                value={source.args}
                language={language}
                onCommit={(args) => updateSource(index, { args })}
              />
            </div>
          ))}
        </div>
      </details>
      <div className="border-t border-[#24282f] bg-[#0d0f12] px-3 py-2">
        <p className="text-[10px] leading-relaxed text-muted-foreground">
          {copy.autoSaveHint}
        </p>
      </div>
    </section>
  )
}

function SourceBusinessArgument({
  argumentKey,
  value,
  language,
  onChange,
}: {
  argumentKey: string
  value: string | number | boolean
  language: WorkflowLanguage
  onChange: (value: string | number | boolean) => void
}) {
  const label = language === "zh-CN"
    ? SOURCE_ARGUMENT_LABELS[argumentKey] ?? argumentKey
    : argumentKey.replace(/[_-]+/g, " ").replace(/\b\w/g, (character) => character.toUpperCase())
  if (typeof value === "boolean") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-[3px] border border-[#252a31] bg-[#0d0f12] px-2.5 py-2">
        <Label className="text-[11px] text-foreground">{label}</Label>
        <Switch checked={value} onCheckedChange={onChange} aria-label={label} />
      </div>
    )
  }
  return (
    <div className="space-y-1">
      <Label className="text-[10px] text-muted-foreground">{label}</Label>
      <Input
        type={typeof value === "number" ? "number" : "text"}
        value={value}
        onChange={(event) => onChange(typeof value === "number" ? Number(event.target.value) : event.target.value)}
        className="h-7 rounded-[2px] border-[#2c3036] bg-[#07080a] px-2 text-[11px] focus-visible:ring-0"
      />
    </div>
  )
}

function SourceArgsEditor({
  sourceId,
  value,
  language,
  onCommit,
}: {
  sourceId: string
  value: Record<string, unknown>
  language: WorkflowLanguage
  onCommit: (value: Record<string, unknown>) => void
}) {
  const copy = INSPECTOR_COPY[language]
  const serialized = JSON.stringify(value, null, 2)
  const [draft, setDraft] = useState(serialized)
  const [error, setError] = useState("")

  useEffect(() => {
    setDraft(serialized)
    setError("")
  }, [serialized])

  const commit = () => {
    try {
      const parsed = JSON.parse(draft) as unknown
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError(copy.jsonObjectRequired)
        return
      }
      setError("")
      onCommit(parsed as Record<string, unknown>)
    } catch {
      setError(copy.invalidJson)
    }
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={`source-args-${sourceId}`} className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
        {copy.parameters}
      </Label>
      <Textarea
        id={`source-args-${sourceId}`}
        rows={3}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        className={cn(houdiniTextareaClass, error && "border-[#7f1d1d]")}
      />
      {error ? <p className="text-[10px] text-[#f87171]">{error}</p> : null}
    </div>
  )
}

function formatJsonParameterValue(value: unknown): string {
  if (!value || typeof value !== "object") return "{}"
  return JSON.stringify(value, null, 2)
}
