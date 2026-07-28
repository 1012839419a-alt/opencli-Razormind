import type {
  AgentPermissions,
  AdapterBinding,
  WorkflowCapability,
  WorkflowNodeKind,
  WorkflowProfile,
  WorkflowProject,
  WorkflowProjectNode,
} from "./schema"
import { parseWorkflowProject } from "./schema"
import { getNodeInternals } from "./node-internals"
import { createParameterInterfaceFromInternals } from "./parameter-interface"
import {
  catalogRuntimeCapability,
  projectedCatalogRuntimeCapability,
  runtimeContractForCapability,
  type WorkflowCapabilitiesResponse,
  type WorkflowRuntimeIOContract,
  type WorkflowRuntimeCapability,
} from "./capabilities"

export type WorkflowNodeCatalogCategory =
  | "trigger"
  | "source"
  | "processing"
  | "flow"
  | "decision"
  | "control"
  | "sink"
  | "output"
  | "package"

export type WorkflowNodeCatalogItem = {
  id: string
  idPrefix: string
  label: string
  description: string
  category: WorkflowNodeCatalogCategory
  profile: WorkflowProfile
  kind: WorkflowNodeKind
  capability: WorkflowCapability
  icon: string
  color: string
  adapter?: string
  requiredAdapters?: AdapterBinding[]
  params: Record<string, unknown>
  topicCollapse?: WorkflowProjectNode["topicCollapse"]
  internals?: WorkflowProjectNode["internals"]
  runtimeCapability?: WorkflowRuntimeCapability
  runtimeContract?: WorkflowRuntimeIOContract
  proposalState?: WorkflowProjectNode["proposalState"]
  agentPermissionPatch?: Partial<AgentPermissions>
  keywords: string[]
}

export const COLLECTION_NEED_CATALOG_ID = "intelligence.input.collection-need"
export const TURBOPUSH_PUBLISH_CATALOG_ID = "intelligence.output.turbopush-publish"

const DIFY_COMPATIBLE_WORKFLOW_BLOCKS: WorkflowNodeCatalogItem[] = [
  {
    id: "workflow.start.webhook",
    idPrefix: "webhook-trigger",
    label: "Webhook Trigger",
    description: "通过外部 HTTP 事件启动工作流",
    category: "trigger",
    profile: "intelligence",
    kind: "schedule",
    capability: "trigger",
    icon: "Webhook",
    color: "var(--chart-1)",
    params: { componentType: "webhook-trigger", compatibility: "dify", method: "POST", path: "" },
    keywords: ["webhook", "trigger", "start", "事件", "触发"],
  },
  {
    id: "workflow.block.agent",
    idPrefix: "agent",
    label: "Agent",
    description: "调用具备工具使用能力的 Agent 完成一个任务",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "summarize",
    icon: "Bot",
    color: "var(--chart-2)",
    params: { componentType: "agent", compatibility: "dify", strategy: "function-calling" },
    keywords: ["agent", "tool", "reasoning", "智能体", "工具调用"],
  },
  {
    id: "workflow.block.agent-v2",
    idPrefix: "agent-v2",
    label: "Agent V2",
    description: "使用可扩展策略与工具集运行 Agent",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "summarize",
    icon: "Bot",
    color: "var(--chart-2)",
    params: { componentType: "agent-v2", compatibility: "dify", strategy: "provider" },
    keywords: ["agent", "provider", "strategy", "智能体"],
  },
  {
    id: "workflow.block.llm",
    idPrefix: "llm",
    label: "LLM",
    description: "调用模型完成生成、理解、分类或结构化输出",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "summarize",
    icon: "Sparkles",
    color: "var(--chart-2)",
    params: { componentType: "llm", compatibility: "dify", model: "", prompt: "" },
    keywords: ["llm", "model", "prompt", "模型", "生成"],
  },
  {
    id: "workflow.block.knowledge-retrieval",
    idPrefix: "knowledge-retrieval",
    label: "Knowledge Retrieval",
    description: "从知识库检索与当前问题相关的上下文",
    category: "processing",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "BookOpen",
    color: "var(--chart-4)",
    params: { componentType: "knowledge-retrieval", compatibility: "dify", datasetIds: [] },
    keywords: ["knowledge", "retrieval", "rag", "知识库", "检索"],
  },
  {
    id: "workflow.block.end",
    idPrefix: "end",
    label: "End",
    description: "结束工作流并声明最终输出变量",
    category: "output",
    profile: "intelligence",
    kind: "sink",
    capability: "store",
    icon: "CircleStop",
    color: "var(--chart-4)",
    params: { componentType: "end", compatibility: "dify", outputs: [] },
    keywords: ["end", "output", "finish", "结束", "输出"],
  },
  {
    id: "workflow.block.direct-answer",
    idPrefix: "direct-answer",
    label: "Direct Answer",
    description: "在对话流程中直接返回文本或变量",
    category: "output",
    profile: "intelligence",
    kind: "notify",
    capability: "send",
    icon: "MessageSquareReply",
    color: "var(--chart-1)",
    params: { componentType: "answer", compatibility: "dify", answer: "" },
    keywords: ["answer", "response", "chat", "直接回复", "回答"],
  },
  {
    id: "workflow.block.question-classifier",
    idPrefix: "question-classifier",
    label: "Question Classifier",
    description: "使用模型把输入问题分配到不同分支",
    category: "decision",
    profile: "intelligence",
    kind: "router",
    capability: "route",
    icon: "ListTree",
    color: "var(--chart-5)",
    params: { componentType: "question-classifier", compatibility: "dify", classes: [] },
    keywords: ["question", "classifier", "route", "问题分类", "分支"],
  },
  {
    id: "workflow.block.if-else",
    idPrefix: "if-else",
    label: "IF / ELSE",
    description: "根据条件表达式把数据路由到不同分支",
    category: "decision",
    profile: "intelligence",
    kind: "router",
    capability: "route",
    icon: "GitBranch",
    color: "var(--chart-5)",
    params: { componentType: "if-else", compatibility: "dify", conditions: [] },
    keywords: ["if", "else", "condition", "条件", "分支"],
  },
  {
    id: "workflow.block.exit-loop",
    idPrefix: "exit-loop",
    label: "Exit Loop",
    description: "满足条件时退出当前循环",
    category: "control",
    profile: "intelligence",
    kind: "control",
    capability: "accept",
    icon: "LogOut",
    color: "var(--chart-5)",
    params: { componentType: "exit-loop", compatibility: "dify" },
    keywords: ["exit", "break", "loop", "退出循环"],
  },
  {
    id: "workflow.block.iteration",
    idPrefix: "iteration",
    label: "Iteration",
    description: "对数组中的每个元素执行同一个子流程",
    category: "flow",
    profile: "intelligence",
    kind: "flow",
    capability: "merge",
    icon: "ListRestart",
    color: "var(--chart-5)",
    params: { componentType: "iteration", compatibility: "dify", parallel: false },
    keywords: ["iteration", "foreach", "array", "迭代", "遍历"],
  },
  {
    id: "workflow.block.loop",
    idPrefix: "loop",
    label: "Loop",
    description: "按终止条件重复执行一个子流程",
    category: "flow",
    profile: "intelligence",
    kind: "flow",
    capability: "merge",
    icon: "Repeat2",
    color: "var(--chart-5)",
    params: { componentType: "loop", compatibility: "dify", maxIterations: 10 },
    keywords: ["loop", "repeat", "while", "循环", "重复"],
  },
  {
    id: "workflow.block.code",
    idPrefix: "code",
    label: "Code",
    description: "运行受控代码处理输入并返回结构化结果",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Code2",
    color: "var(--chart-2)",
    params: { componentType: "code", compatibility: "dify", language: "javascript", code: "" },
    keywords: ["code", "javascript", "python", "代码", "脚本"],
  },
  {
    id: "workflow.block.template-transform",
    idPrefix: "template-transform",
    label: "Template Transform",
    description: "使用模板把上游变量转换为文本",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Braces",
    color: "var(--chart-2)",
    params: { componentType: "template-transform", compatibility: "dify", template: "" },
    keywords: ["template", "jinja", "transform", "模板", "转换"],
  },
  {
    id: "workflow.block.variable-aggregator",
    idPrefix: "variable-aggregator",
    label: "Variable Aggregator",
    description: "把多个分支中的变量聚合为统一输出",
    category: "flow",
    profile: "intelligence",
    kind: "flow",
    capability: "merge",
    icon: "GitMerge",
    color: "var(--chart-5)",
    params: { componentType: "variable-aggregator", compatibility: "dify", variables: [] },
    keywords: ["variable", "aggregate", "merge", "变量聚合", "合并"],
  },
  {
    id: "workflow.block.document-extractor",
    idPrefix: "document-extractor",
    label: "Document Extractor",
    description: "从上传的文档中提取可供下游处理的文本",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "FileText",
    color: "var(--chart-2)",
    params: { componentType: "document-extractor", compatibility: "dify", files: [] },
    keywords: ["document", "extract", "file", "文档", "提取"],
  },
  {
    id: "workflow.block.variable-assigner",
    idPrefix: "variable-assigner",
    label: "Variable Assigner",
    description: "在流程上下文中写入或更新变量",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Variable",
    color: "var(--chart-2)",
    params: { componentType: "assigner", compatibility: "dify", assignments: [] },
    keywords: ["variable", "assign", "state", "变量", "赋值"],
  },
  {
    id: "workflow.block.parameter-extractor",
    idPrefix: "parameter-extractor",
    label: "Parameter Extractor",
    description: "使用模型从自然语言中抽取结构化参数",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "ListFilter",
    color: "var(--chart-2)",
    params: { componentType: "parameter-extractor", compatibility: "dify", parameters: [] },
    keywords: ["parameter", "extract", "structured", "参数", "抽取"],
  },
  {
    id: "workflow.block.http-request",
    idPrefix: "http-request",
    label: "HTTP Request",
    description: "在流程中发起可配置的 HTTP 请求",
    category: "processing",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Globe",
    color: "var(--chart-4)",
    params: { componentType: "http-request", compatibility: "dify", method: "GET", url: "" },
    keywords: ["http", "request", "api", "网络请求", "接口"],
  },
  {
    id: "workflow.block.list-filter",
    idPrefix: "list-filter",
    label: "List Filter",
    description: "筛选、排序或截断数组数据",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "ListFilter",
    color: "var(--chart-2)",
    params: { componentType: "list-filter", compatibility: "dify", conditions: [], limit: null },
    keywords: ["list", "filter", "sort", "数组", "筛选"],
  },
]

const JIN10_ADAPTER: AdapterBinding = {
  id: "jin10-kuaixun",
  type: "source",
  provider: "jin10",
  mode: "fixture",
  config: { feed: "kuaixun" },
}

const RSS_ADAPTER: AdapterBinding = {
  id: "rss-feed",
  type: "source",
  provider: "rss",
  mode: "live",
  config: { channel: "rss" },
}

const HTTP_ADAPTER: AdapterBinding = {
  id: "http-api",
  type: "source",
  provider: "http",
  mode: "live",
  config: { channel: "http", method: "GET" },
}

const WEBHOOK_NOTIFY_ADAPTER: AdapterBinding = {
  id: "webhook-notifier",
  type: "notification",
  provider: "webhook",
  mode: "webhook",
  config: { notifierType: "webhook", target: "webhook" },
}

const TURBOPUSH_ADAPTER: AdapterBinding = {
  id: "turbopush-local",
  type: "notification",
  provider: "turbopush",
  mode: "live",
  config: { channel: "turbopush", mcpServer: "turbo-push", resourceMode: "auto" },
}

export type OpenCLISourceSlot = {
  id: string
  label: string
  sourceGroup: string
  site: string
  command: string
  args: Record<string, unknown>
  adapterId?: string
  format?: string
  mode?: string
  profileId?: string
  profileBinding?: string
  sessionPolicy?: string
  workerTags?: string[]
  resourceTags?: string[]
}

export const DEFAULT_OPENCLI_HDA_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "bilibili",
    label: "Bilibili Search",
    sourceGroup: "video",
    site: "bilibili",
    command: "search",
    args: { keyword: "ai" },
  },
  {
    id: "xiaohongshu",
    label: "Xiaohongshu Search",
    sourceGroup: "social",
    site: "xiaohongshu",
    command: "search",
    args: { keyword: "ai" },
  },
]

export function opencliAdaptersForSourceSlots(sources: OpenCLISourceSlot[]): AdapterBinding[] {
  const adapters = sources.map((source) => ({
    id: source.adapterId ?? opencliAdapterId(source.site),
    type: "source" as const,
    provider: "opencli",
    mode: "live" as const,
    config: { channel: "opencli" },
  }))
  return Array.from(new Map(adapters.map((adapter) => [adapter.id, adapter])).values())
}

export function buildOpenCLIMultiSourceHDAInternals(sources: OpenCLISourceSlot[]): WorkflowProjectNode["internals"] {
  const sourceGroups = sources.map((source) => source.sourceGroup || source.site)
  const sourcePoolNode = {
    id: "source-pool",
    kind: "agent" as const,
    capability: "normalize" as const,
    params: { sourceCount: sources.length, sourceGroups, fanout: "parallel" },
    ui: {
      label: "Source Pool",
      description: "Fanout source intent into parallel OpenCLI source slots",
      icon: "Network",
      color: "var(--chart-4)",
      catalogId: "intelligence.source.pool",
      position: { x: 0, y: Math.max(0, ((sources.length - 1) * 150) / 2) },
    },
  }
  const sourceNodes = sources.map((source, index) => ({
    id: opencliSourceNodeId(source),
    kind: "source" as const,
    capability: "fetch" as const,
    adapter: source.adapterId ?? opencliAdapterId(source.site),
    params: {
      site: source.site,
      command: source.command,
      args: source.args,
      sourceGroup: source.sourceGroup,
      ...(source.format ? { format: source.format } : {}),
      ...(source.mode ? { mode: source.mode } : {}),
      ...(source.profileId ? { profileId: source.profileId } : {}),
      ...(source.profileBinding ? { profileBinding: source.profileBinding } : {}),
      ...(source.sessionPolicy ? { sessionPolicy: source.sessionPolicy } : {}),
      ...(source.workerTags ? { workerTags: source.workerTags } : {}),
      ...(source.resourceTags ? { resourceTags: source.resourceTags } : {}),
    },
    ui: {
      label: source.label,
      description: `${source.site} ${source.command}`,
      icon: "Globe",
      color: "var(--chart-4)",
      catalogId: "intelligence.source.opencli-slot",
      position: { x: 280, y: index * 150 },
    },
  }))
  const midpointY = Math.max(0, ((sourceNodes.length - 1) * 150) / 2)
  const outputNode = {
    id: "collection-output",
    kind: "inbox" as const,
    capability: "store" as const,
    params: { queue: "opencli-hda-output", archive: false },
    ui: {
      label: "Collection Output",
      description: "Expose normalized items as the package output",
      icon: "Inbox",
      color: "var(--chart-4)",
      catalogId: "intelligence.output.collection-result",
      position: { x: 920, y: midpointY },
    },
  }
  return {
    locked: true,
    nodes: [
      sourcePoolNode,
      ...sourceNodes,
      {
        id: "internal-normalize",
        kind: "agent",
        capability: "normalize",
        params: { language: "zh-CN", preserveSourceRefs: true },
        ui: {
          label: "Normalize Items",
          description: "Normalize OpenCLI source slot results",
          icon: "ArrowRightLeft",
          color: "var(--chart-2)",
          catalogId: "intelligence.processing.normalize",
          position: { x: 620, y: midpointY },
        },
      },
      outputNode,
    ],
    edges: [
      ...sourceNodes.map((sourceNode) => ({
        id: `source-pool-${sourceNode.id}`,
        source: "source-pool",
        target: sourceNode.id,
        sourcePort: "out",
        targetPort: "in",
      })),
      ...sourceNodes.map((sourceNode) => ({
        id: `${sourceNode.id}-normalize`,
        source: sourceNode.id,
        target: "internal-normalize",
        sourcePort: "out",
        targetPort: "in",
      })),
      {
        id: "internal-normalize-output",
        source: "internal-normalize",
        target: "collection-output",
        sourcePort: "out",
        targetPort: "in",
      },
    ],
  }
}

function opencliAdapterId(site: string): string {
  return `opencli-${safeIdPart(site)}`
}

function opencliSourceNodeId(source: OpenCLISourceSlot): string {
  return `source-${safeIdPart(source.id || source.sourceGroup || source.site)}`
}

function safeIdPart(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "source"
}

export const WORKFLOW_NODE_CATALOG: WorkflowNodeCatalogItem[] = [
  ...DIFY_COMPATIBLE_WORKFLOW_BLOCKS,
  {
    id: COLLECTION_NEED_CATALOG_ID,
    idPrefix: "collection-need",
    label: "Collection Need",
    description: "用户只输入采集需求，由后端 demand-draft 组装真实节点 patch",
    category: "trigger",
    profile: "intelligence",
    kind: "schedule",
    capability: "trigger",
    icon: "MessageSquare",
    color: "var(--chart-1)",
    params: { text: "抓小红书热帖", locale: "zh-CN", mode: "demand-draft" },
    keywords: ["need", "demand", "input", "manual", "需求", "输入", "采集"],
  },
  {
    id: "intelligence.schedule.cron",
    idPrefix: "schedule",
    label: "Cron Schedule",
    description: "按 cron/interval 周期触发情报工作流",
    category: "trigger",
    profile: "intelligence",
    kind: "schedule",
    capability: "trigger",
    icon: "Clock",
    color: "var(--chart-1)",
    params: { interval: "5m", timezone: "Asia/Shanghai" },
    keywords: ["schedule", "cron", "hourly", "daily", "定时", "触发"],
  },
  {
    id: "intelligence.source.jin10",
    idPrefix: "source-jin10",
    label: "JIN10 Source",
    description: "读取金十快讯 fixture/live feed",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Globe",
    color: "var(--chart-4)",
    adapter: JIN10_ADAPTER.id,
    requiredAdapters: [JIN10_ADAPTER],
    params: { limit: 20, importantOnly: false, channel: "kuaixun" },
    keywords: ["jin10", "金十", "source", "news", "kuaixun", "fetch"],
  },
  {
    id: "intelligence.source.rss",
    idPrefix: "source-rss",
    label: "RSS / Atom Reader",
    description: "读取已有的 RSS 或 Atom 地址，并以 sourceGroup 保留来源分组和血缘",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Rss",
    color: "var(--chart-4)",
    adapter: RSS_ADAPTER.id,
    requiredAdapters: [RSS_ADAPTER],
    params: {
      feedUrl: "https://www.federalreserve.gov/feeds/press_all.xml",
      maxEntries: 20,
      sourceGroup: "macro-policy",
      site: "federal-reserve",
    },
    keywords: ["rss", "atom", "reader", "feed", "finance", "news", "财经", "订阅", "数据源", "读取"],
  },
  {
    id: "intelligence.source.rsshub",
    idPrefix: "source-rsshub",
    label: "RSSHub Reader",
    description: "通过受管 RSSHub Provider 和 route 生成订阅源，再输出标准 RSS 条目",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Rss",
    color: "var(--chart-4)",
    adapter: RSS_ADAPTER.id,
    requiredAdapters: [RSS_ADAPTER],
    params: {
      providerId: "",
      generatorType: "rsshub",
      route: "",
      routeParameters: {},
      generatorSelection: { route: "", parameters: {} },
      maxEntries: 20,
      sourceGroup: "rsshub",
      site: "rsshub",
    },
    keywords: ["rsshub", "rss hub", "reader", "route", "feed", "订阅生成", "路由", "读取"],
  },
  {
    id: "intelligence.source.rss-bridge",
    idPrefix: "source-rss-bridge",
    label: "RSS-Bridge Reader",
    description: "通过受管 RSS-Bridge Provider 为缺少订阅源的网页生成并读取 RSS",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Rss",
    color: "var(--chart-4)",
    adapter: RSS_ADAPTER.id,
    requiredAdapters: [RSS_ADAPTER],
    params: {
      providerId: "",
      generatorType: "rss_bridge",
      bridge: "",
      bridgeParameters: {},
      generatorSelection: { bridge: "", parameters: {} },
      maxEntries: 20,
      sourceGroup: "rss-bridge",
      site: "rss-bridge",
    },
    keywords: ["rss-bridge", "rss bridge", "reader", "bridge", "feed", "网页订阅", "读取"],
  },
  {
    id: "intelligence.source.http",
    idPrefix: "source-http",
    label: "HTTP / API Reader",
    description: "通过受控 GET/POST 网络请求读取 JSON API，作为可与其他来源并行组合的原子节点",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Globe",
    color: "var(--chart-4)",
    adapter: HTTP_ADAPTER.id,
    requiredAdapters: [HTTP_ADAPTER],
    params: {
      url: "",
      method: "GET",
      resultPath: "",
      headers: {},
      query: {},
      sourceGroup: "http-api",
      site: "http-api",
    },
    keywords: ["http", "https", "api", "rest", "json", "reader", "network", "网络", "接口", "读取"],
  },
  {
    id: "intelligence.processing.normalize",
    idPrefix: "normalize",
    label: "Normalize Items",
    description: "统一字段、语言和时间格式",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "ArrowRightLeft",
    color: "var(--chart-2)",
    params: { language: "zh-CN", preserveSourceRefs: true },
    keywords: ["normalize", "clean", "format", "标准化", "清洗"],
  },
  {
    id: "intelligence.processing.dedupe",
    idPrefix: "dedupe",
    label: "Dedupe Items",
    description: "按标题、时间和来源去重",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "dedupe",
    icon: "Filter",
    color: "var(--chart-2)",
    params: { key: "title+source+publishedAt", window: "24h" },
    keywords: ["dedupe", "duplicate", "去重", "重复"],
  },
  {
    id: "intelligence.flow.merge",
    idPrefix: "merge",
    label: "Merge",
    description: "Houdini-style typed fan-in，合并多路候选流并保留 lineage",
    category: "flow",
    profile: "intelligence",
    kind: "flow",
    capability: "merge",
    icon: "GitMerge",
    color: "var(--chart-5)",
    params: {
      strategy: "concat",
      preserveLineage: true,
      inputType: "recordCandidate[]",
      outputType: "recordCandidate[]",
    },
    keywords: ["merge", "join", "fan-in", "lineage", "合并", "汇流"],
  },
  {
    id: "intelligence.agent.summary",
    idPrefix: "summary",
    label: "LLM Summary",
    description: "生成短摘要和影响解释",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "summarize",
    icon: "Sparkles",
    color: "var(--chart-2)",
    params: { model: "deepseek", style: "macro-brief", maxChars: 280 },
    keywords: ["deepseek", "gpt", "claude", "llm", "agent", "summary", "摘要"],
  },
  {
    id: "intelligence.agent.score",
    idPrefix: "score",
    label: "Importance Score",
    description: "按影响范围和紧急度打分",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "score",
    icon: "Sigma",
    color: "var(--chart-3)",
    params: { threshold: 0.7, dimensions: ["market", "policy", "urgency"] },
    keywords: ["score", "rating", "importance", "打分", "重要性"],
  },
  {
    id: "intelligence.agent.tag",
    idPrefix: "tag",
    label: "Auto Tag",
    description: "给条目打主题、市场和风险标签",
    category: "processing",
    profile: "intelligence",
    kind: "agent",
    capability: "tag",
    icon: "Code",
    color: "var(--chart-3)",
    params: { taxonomy: ["macro", "fx", "commodity", "policy", "risk"] },
    keywords: ["tag", "label", "topic", "标签", "分类"],
  },
  {
    id: "intelligence.router.importance",
    idPrefix: "router-importance",
    label: "Importance Router",
    description: "按分数和条件路由到 Inbox/Notify",
    category: "decision",
    profile: "intelligence",
    kind: "router",
    capability: "route",
    icon: "GitBranch",
    color: "var(--chart-5)",
    params: { expression: "item.important === true || item.score >= 0.7" },
    keywords: ["score", "router", "condition", "threshold", "路由", "阈值"],
  },
  {
    id: "intelligence.control.record-acceptance",
    idPrefix: "record-acceptance",
    label: "Record Acceptance Gate",
    description: "把 Record Candidate 通过 schema、去重、质量和 lineage 检查后接收为 Record",
    category: "control",
    profile: "intelligence",
    kind: "control",
    capability: "accept",
    icon: "BadgeCheck",
    color: "var(--chart-3)",
    params: {
      mode: "automatic_with_review",
      schema: "record.v1",
      dedupe: "required",
      lineageRequired: true,
      minQuality: 0,
    },
    keywords: ["record", "acceptance", "gate", "quality", "lineage", "入库", "审核"],
  },
  {
    id: "intelligence.output.inbox",
    idPrefix: "inbox",
    label: "Inbox Store",
    description: "保存到人工复核队列",
    category: "output",
    profile: "intelligence",
    kind: "inbox",
    capability: "store",
    icon: "Inbox",
    color: "var(--chart-4)",
    params: { queue: "macro-watch", archive: true },
    keywords: ["inbox", "store", "cache", "archive", "收件箱", "归档"],
  },
  {
    id: "intelligence.sink.records",
    idPrefix: "record-sink",
    label: "Record Sink",
    description: "把已接收的 Record 写入 records 系统，保留 lineage 和 run trace 指针",
    category: "sink",
    profile: "intelligence",
    kind: "sink",
    capability: "store",
    icon: "Database",
    color: "var(--chart-4)",
    params: { target: "records", writeMode: "append", preserveLineage: true },
    keywords: ["record", "sink", "database", "records", "落库", "存储"],
  },
  {
    id: "intelligence.output.webhook",
    idPrefix: "notify",
    label: "Webhook Notify",
    description: "通过后端 guarded webhook notifier 发送工作流通知",
    category: "output",
    profile: "intelligence",
    kind: "notify",
    capability: "send",
    icon: "Bell",
    color: "var(--chart-1)",
    adapter: WEBHOOK_NOTIFY_ADAPTER.id,
    requiredAdapters: [WEBHOOK_NOTIFY_ADAPTER],
    params: { template: "brief", target: "webhook" },
    keywords: ["feishu", "wecom", "tg", "telegram", "qq", "notify", "webhook", "通知"],
  },
  {
    id: TURBOPUSH_PUBLISH_CATALOG_ID,
    idPrefix: "turbopush-publish",
    label: "TurboPush Publish",
    description: "通过本机 TurboPush 服务发布文章/图文/视频到已登录平台账号",
    category: "output",
    profile: "intelligence",
    kind: "notify",
    capability: "send",
    icon: "Send",
    color: "var(--state-action)",
    adapter: TURBOPUSH_ADAPTER.id,
    requiredAdapters: [TURBOPUSH_ADAPTER],
    params: {
      contentType: "graph_text",
      contentSource: "upstream",
      title: "{{item.title}}",
      markdown: "{{item.markdown}}",
      desc: "{{item.summary}}",
      files: [],
      thumb: [],
      targetPlatforms: ["xiaohongshu"],
      accountSelector: "logged_accounts_by_platform",
      platformSettings: {},
      syncDraft: false,
    },
    keywords: [
      "turbopush",
      "publish",
      "send",
      "wechat",
      "douyin",
      "xiaohongshu",
      "youtube",
      "bilibili",
      "多平台",
      "发布",
      "发送",
    ],
  },
  {
    id: "package.collection.pipeline",
    idPrefix: "pkg-collection",
    label: "Collection Pipeline",
    description: "封装调度触发、多源采集（JIN10/RSS/HTTP）、标准化、去重和富化的采集管线",
    category: "package",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Globe",
    color: "var(--chart-4)",
    adapter: JIN10_ADAPTER.id,
    requiredAdapters: [JIN10_ADAPTER],
    params: { template: "collection-pipeline", runtime: "fixture", lockedInternals: true },
    keywords: ["package", "collection", "source", "rss", "http", "采集", "封装"],
  },
  {
    id: "intelligence.source.pool",
    idPrefix: "source-pool",
    label: "Source Pool",
    description: "把业务来源组展开为并行 source slots，资源由 runtime resolver 隐式处理",
    category: "source",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Network",
    color: "var(--chart-4)",
    params: { sourceCount: 2, sourceGroups: ["video", "social"], fanout: "parallel" },
    keywords: ["source", "pool", "fanout", "registry", "来源池", "数据源"],
  },
  {
    id: "intelligence.source.opencli-slot",
    idPrefix: "source-opencli",
    label: "OpenCLI Source Slot",
    description: "一个由 HDA/source planner 生成的 OpenCLI source 槽位，运行时交给 OpenCLI channel 执行",
    category: "source",
    profile: "intelligence",
    kind: "source",
    capability: "fetch",
    icon: "Globe",
    color: "var(--chart-4)",
    params: { site: "bilibili", command: "search", sourceGroup: "video", args: { keyword: "ai" } },
    keywords: ["opencli", "source", "slot", "bilibili", "xiaohongshu", "adapter", "来源槽"],
  },
  {
    id: "intelligence.output.collection-result",
    idPrefix: "collection-output",
    label: "Collection Output",
    description: "把 HDA 内部标准化结果暴露为可审计的 items[] 输出",
    category: "output",
    profile: "intelligence",
    kind: "inbox",
    capability: "store",
    icon: "Inbox",
    color: "var(--chart-4)",
    params: { queue: "opencli-hda-output", archive: false },
    keywords: ["output", "items", "collection", "result", "采集输出", "结果"],
  },
  {
    id: "package.opencli.multi-source-hda",
    idPrefix: "pkg-opencli-hda",
    label: "OpenCLI Multi-source HDA",
    description: "封装可扩展 OpenCLI source slot 并行 fanout 和内部标准化",
    category: "package",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Network",
    color: "var(--chart-4)",
    requiredAdapters: opencliAdaptersForSourceSlots(DEFAULT_OPENCLI_HDA_SOURCES),
    params: {
      template: "opencli-multi-source",
      runtime: "iii",
      lockedInternals: true,
      execution: {
        fanout: "parallel",
      },
      sources: DEFAULT_OPENCLI_HDA_SOURCES,
      aiCallable: {
        schema: "opencli.multi_source_hda.v1",
        editable: ["sources", "sources[].args"],
        sourceMode: "parallel",
      },
    },
    topicCollapse: {
      groupId: "opencli-package",
      nodeCount: DEFAULT_OPENCLI_HDA_SOURCES.length + 3,
      mode: "locked",
      packageInternal: true,
    },
    internals: buildOpenCLIMultiSourceHDAInternals(DEFAULT_OPENCLI_HDA_SOURCES),
    keywords: ["package", "hda", "opencli", "bilibili", "xiaohongshu", "multi-source", "采集", "封装"],
  },
  {
    id: "package.dispatch.fanout",
    idPrefix: "pkg-dispatch",
    label: "Dispatch Fanout",
    description: "封装重要性路由、限流和 Webhook/Telegram/邮件多通道发送与 Postgres 存档",
    category: "package",
    profile: "intelligence",
    kind: "notify",
    capability: "send",
    icon: "Bell",
    color: "var(--chart-1)",
    adapter: WEBHOOK_NOTIFY_ADAPTER.id,
    requiredAdapters: [WEBHOOK_NOTIFY_ADAPTER],
    params: { template: "dispatch-fanout", runtime: "mock", lockedInternals: true },
    keywords: ["package", "dispatch", "fanout", "telegram", "email", "发送", "分发", "封装"],
  },
  {
    id: "package.intelligence.pipeline",
    idPrefix: "pkg-intelligence",
    label: "Intelligence Pipeline",
    description: "封装定时抓取、标准化、摘要评分、复核和通知的情报流水线",
    category: "package",
    profile: "intelligence",
    kind: "agent",
    capability: "normalize",
    icon: "Network",
    color: "var(--chart-2)",
    params: { template: "jin10-intelligence", runtime: "fixture", lockedInternals: true },
    keywords: ["package", "dop", "intelligence", "pipeline", "情报", "封装"],
  },
  {
    id: "package.ops.event",
    idPrefix: "pkg-ops-event",
    label: "Ops Event",
    description: "封装触发、队列、重试、日志和执行证据的任务事件",
    category: "package",
    profile: "intelligence",
    kind: "action",
    capability: "send",
    icon: "ServerCog",
    color: "var(--chart-4)",
    params: { template: "ops-event", runtime: "template", lockedInternals: true },
    keywords: ["package", "ops", "event", "job", "automation", "任务"],
  },
  {
    id: "package.ops.monitor-guard",
    idPrefix: "pkg-monitor",
    label: "Monitor Guard",
    description: "封装指标采集、阈值、delta 和限流的监控闸门",
    category: "package",
    profile: "intelligence",
    kind: "router",
    capability: "route",
    icon: "Activity",
    color: "var(--chart-4)",
    params: { template: "monitor-guard", runtime: "template", lockedInternals: true },
    keywords: ["package", "monitor", "guard", "metric", "alert", "监控"],
  },
  {
    id: "package.ops.alert-response",
    idPrefix: "pkg-alert",
    label: "Alert Response",
    description: "封装告警分派、通知、工单、快照和升级动作",
    category: "package",
    profile: "intelligence",
    kind: "notify",
    capability: "send",
    icon: "Bell",
    color: "var(--chart-1)",
    params: { template: "alert-response", runtime: "template", lockedInternals: true },
    keywords: ["package", "alert", "response", "ticket", "snapshot", "告警"],
  },
  {
    id: "package.ai.prompt-experiment",
    idPrefix: "pkg-prompt-exp",
    label: "Prompt Experiment",
    description: "封装 prompt 版本、测试用例、模型对比和实验记录",
    category: "package",
    profile: "intelligence",
    kind: "agent",
    capability: "summarize",
    icon: "FlaskConical",
    color: "var(--state-action)",
    params: { template: "prompt-experiment", runtime: "mock", lockedInternals: true },
    keywords: ["package", "prompt", "experiment", "model", "eval", "实验"],
  },
  {
    id: "package.verify.regression-gate",
    idPrefix: "pkg-regression",
    label: "Regression Gate",
    description: "封装 dataset、evaluator、scorecard 和回归门禁",
    category: "package",
    profile: "intelligence",
    kind: "router",
    capability: "route",
    icon: "ShieldCheck",
    color: "#4ade80",
    params: { template: "regression-gate", runtime: "mock", lockedInternals: true },
    keywords: ["package", "regression", "scorecard", "coverage", "gate", "回归"],
  },
  {
    id: "package.map.knowledge-map",
    idPrefix: "pkg-knowledge-map",
    label: "Knowledge Map",
    description: "封装来源锚点、语义连线、主题折叠和知识导出",
    category: "package",
    profile: "intelligence",
    kind: "action",
    capability: "store",
    icon: "Network",
    color: "var(--chart-3)",
    params: { template: "knowledge-map", runtime: "template", lockedInternals: true },
    keywords: ["package", "knowledge", "map", "turnmap", "obsidian", "知识图"],
  },
  {
    id: "package.review.human-review",
    idPrefix: "pkg-human-review",
    label: "Human Review",
    description: "封装人工审核、Inbox、审批分支和审计证据",
    category: "package",
    profile: "intelligence",
    kind: "inbox",
    capability: "store",
    icon: "Inbox",
    color: "var(--chart-4)",
    params: { template: "human-review", runtime: "template", lockedInternals: true },
    keywords: ["package", "human", "review", "approval", "inbox", "人工"],
  },
]

export function getWorkflowNodeCatalog(
  profile: WorkflowProfile,
  capabilities?: WorkflowCapabilitiesResponse | null,
): WorkflowNodeCatalogItem[] {
  const staticCatalog = WORKFLOW_NODE_CATALOG.filter((item) => item.profile === profile).map((item) => {
    const runtimeCapability = projectedCatalogRuntimeCapability(
      catalogRuntimeCapability(capabilities, item.id),
      item,
      Boolean(capabilities),
    )
    return {
      ...item,
      runtimeCapability,
      runtimeContract: runtimeContractForCapability(runtimeCapability),
    }
  })
  if (profile !== "intelligence") return staticCatalog
  const dynamicPluginCatalog = (capabilities?.catalog ?? []).flatMap((runtimeCapability) => {
    const item = pluginNodeCatalogItem(runtimeCapability)
    return item ? [item] : []
  })
  return [...staticCatalog, ...dynamicPluginCatalog]
}

export function workflowCatalogItemLocked(item: WorkflowNodeCatalogItem): boolean {
  const manifest = readCatalogRecord(item.runtimeCapability?.manifest)
  const canvas = readCatalogRecord(manifest?.canvas)
  return canvas?.locked === true
}

export function workflowCatalogPluginProvenance(
  item: WorkflowNodeCatalogItem,
): { providerKey: string; version: string } | null {
  const manifest = readCatalogRecord(item.runtimeCapability?.manifest)
  const plugin = readCatalogRecord(manifest?.plugin)
  const providerKey = typeof plugin?.providerKey === "string" ? plugin.providerKey : null
  const version = typeof plugin?.version === "string" ? plugin.version : null
  return providerKey && version ? { providerKey, version } : null
}

function pluginNodeCatalogItem(
  runtimeCapability: WorkflowRuntimeCapability,
): WorkflowNodeCatalogItem | null {
  if (runtimeCapability.source !== "backend.services.plugin_registry_service") return null
  const kind = pluginNodeKind(runtimeCapability.kind)
  const capability = pluginNodeCapability(runtimeCapability.capability)
  if (!kind || !capability) return null
  const manifest = readCatalogRecord(runtimeCapability.manifest)
  const plugin = readCatalogRecord(manifest?.plugin)
  const providerKey = typeof plugin?.providerKey === "string" ? plugin.providerKey : "plugin"
  const version = typeof plugin?.version === "string" ? plugin.version : "unknown"
  const family = typeof plugin?.family === "string" ? plugin.family : "tool"
  return {
    id: runtimeCapability.id,
    idPrefix: safeIdPart(`${providerKey}-${runtimeCapability.label}`),
    label: runtimeCapability.label,
    description: `${providerKey} · ${version} · ${runtimeCapability.reason ?? "等待运行适配器"}`,
    category: pluginCatalogCategory(family),
    profile: "intelligence",
    kind,
    capability,
    icon: pluginCatalogIcon(family),
    color: "var(--muted-foreground)",
    params: {
      pluginInstallationId: plugin?.installationId,
      pluginProviderKey: providerKey,
      pluginVersion: version,
      pluginCapabilityId: plugin?.capabilityId,
    },
    runtimeCapability,
    keywords: [
      "plugin",
      "dify",
      providerKey,
      version,
      family,
      runtimeCapability.label,
      ...runtimeCapability.tags,
    ],
  }
}

function pluginNodeKind(value: string | null | undefined): WorkflowNodeKind | null {
  return ["schedule", "source", "agent", "action"].includes(value ?? "")
    ? value as WorkflowNodeKind
    : null
}

function pluginNodeCapability(
  value: string | null | undefined,
): WorkflowCapability | null {
  return ["trigger", "fetch", "summarize", "store"].includes(value ?? "")
    ? value as WorkflowCapability
    : null
}

function pluginCatalogCategory(family: string): WorkflowNodeCatalogCategory {
  if (family === "trigger") return "trigger"
  if (family === "datasource") return "source"
  if (family === "agent_strategy") return "processing"
  return "output"
}

function pluginCatalogIcon(family: string): string {
  if (family === "trigger") return "Clock"
  if (family === "datasource") return "Database"
  if (family === "agent_strategy") return "Bot"
  return "Puzzle"
}

function readCatalogRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

export function createWorkflowNodeFromCatalog(
  item: WorkflowNodeCatalogItem,
  id: string,
  position: { x: number; y: number },
): WorkflowProjectNode {
  const parameterInterface = createParameterInterfaceFromInternals(
    id,
    getNodeInternals({
      id,
      kind: item.kind,
      capability: item.capability,
      adapter: item.adapter,
      params: item.params,
      ui: { catalogId: item.id },
    }),
  )

  return {
    id,
    kind: item.kind,
    capability: item.capability,
    adapter: item.adapter,
    params: cloneCatalogValue(item.params) ?? {},
    proposalState: item.proposalState,
    topicCollapse: cloneCatalogValue(item.topicCollapse),
    parameterInterface,
    internals: cloneCatalogValue(item.internals),
    ui: {
      label: item.label,
      description: item.description,
      icon: item.icon,
      color: item.color,
      position,
      catalogId: item.id,
      runtimeCapability: cloneCatalogValue(item.runtimeCapability),
      runtimeContract: cloneCatalogValue(item.runtimeContract),
    },
  }
}

export type WorkflowOperatorNodeOptions = {
  label?: string
  description?: string
}

/**
 * Build the Dify-style business layer without replacing the existing OpenCLI node.
 *
 * The operator is a structural/governance container (L1). The catalog node remains
 * intact as its implementation child (L2), including its adapter, parameter
 * interface, runtime contract, and deeper internal network.
 */
export function createOperatorNodeFromCatalog(
  item: WorkflowNodeCatalogItem,
  operatorId: string,
  implementationId: string,
  position: { x: number; y: number },
  options: WorkflowOperatorNodeOptions = {},
): WorkflowProjectNode {
  const implementation = createWorkflowNodeFromCatalog(item, implementationId, { x: 120, y: 160 })
  const implementationNode: WorkflowProjectNode = {
    ...implementation,
    ui: {
      ...implementation.ui,
      networkRole: "implementation",
    },
  }

  return {
    id: operatorId,
    kind: item.kind,
    capability: item.capability,
    params: {
      operator: {
        execution: "internals",
        implementationCatalogId: item.id,
        implementationNodeId: implementationId,
      },
    },
    internals: {
      locked: false,
      nodes: [implementationNode],
      edges: [],
    },
    miniNetwork: {
      nodes: 1,
      edges: 0,
      mode: "title-only",
    },
    ui: {
      label: options.label ?? item.label,
      description: options.description ?? `${item.description}；双击进入 OpenCLI 实现网络`,
      icon: item.icon,
      color: item.color,
      position,
      networkRole: "operator",
      implementationCatalogId: item.id,
    },
  }
}

export function addCatalogNodeToWorkflowProject(
  project: WorkflowProject,
  item: WorkflowNodeCatalogItem,
  id: string,
  position: { x: number; y: number },
): WorkflowProject {
  const existingAdapters = new Set(project.adapters.map((adapter) => adapter.id))
  const requiredAdapters = (item.requiredAdapters ?? []).filter((adapter) => !existingAdapters.has(adapter.id))
  return parseWorkflowProject({
    ...project,
    agentPermissions: {
      ...project.agentPermissions,
      ...item.agentPermissionPatch,
    },
    adapters: [...project.adapters, ...requiredAdapters],
    nodes: [
      ...project.nodes,
      item.category === "package"
        ? createOperatorNodeFromCatalog(item, id, `${id}-implementation`, position)
        : createWorkflowNodeFromCatalog(item, id, position),
    ],
  })
}

function cloneCatalogValue<T>(value: T | undefined): T | undefined {
  return value === undefined ? undefined : (JSON.parse(JSON.stringify(value)) as T)
}
