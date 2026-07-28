import { PACKAGED_WORKFLOW_PROJECT } from "./collection-pipeline"
import {
  WORKFLOW_NODE_CATALOG,
  buildOpenCLIMultiSourceHDAInternals,
  createWorkflowNodeFromCatalog,
  opencliAdaptersForSourceSlots,
  type OpenCLISourceSlot,
  type WorkflowNodeCatalogItem,
} from "./node-catalog"
import { parseWorkflowProject, type WorkflowProjectNode } from "./schema"

export const DOMESTIC_OODA_SOURCE_GROUPS = [
  "market",
  "filings",
  "macro",
  "news",
  "social",
] as const

export const DOMESTIC_OODA_SOURCE_GAPS = [
  {
    site: "gelonghui",
    status: "unavailable",
    reason: "当前 OpenCLI 注册表没有格隆汇命令；保留为明确缺口，不生成伪节点。",
  },
  {
    site: "jin10",
    command: "kuaixun",
    status: "degraded",
    reason: "命令已注册，但最近一次真实请求为空；运行时按 empty 展示。",
  },
  {
    site: "cninfo",
    command: "disclosure-pdf",
    status: "degraded",
    reason: "命令已注册，但最近一次真实请求为空；保留官方 PDF 来源并公开健康状态。",
  },
] as const

export const ASHARE_OPENCLI_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "market-breadth",
    label: "沪深京 A 股行情全景",
    sourceGroup: "market",
    site: "eastmoney",
    command: "gridlist",
    args: { market: "hs-a", sort: "turnover", limit: 100 },
  },
  {
    id: "watchlist-quotes",
    label: "A 股样本实时行情",
    sourceGroup: "market",
    site: "eastmoney",
    command: "quote",
    args: {},
    positionalArgs: ["600519,000001,300750"],
  },
  {
    id: "ths-hot",
    label: "同花顺强势股与题材归因",
    sourceGroup: "market",
    site: "ths",
    command: "hot",
    args: { limit: 50 },
  },
  {
    id: "tdx-hot-rank",
    label: "通达信股票热度排行",
    sourceGroup: "market",
    site: "tdx",
    command: "hot-rank",
    args: { limit: 20 },
  },
  {
    id: "fundamentals",
    label: "东方财富上市公司财务摘要",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "bbsj-summary",
    args: { code: "600519", limit: 8 },
  },
  {
    id: "announcements",
    label: "东方财富沪深京上市公司公告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "announcement",
    args: { market: "SHA,SZA,BJA", limit: 100 },
  },
  {
    id: "sse-announcements",
    label: "上交所官方公告与 PDF",
    sourceGroup: "filings",
    site: "sse",
    command: "announcements",
    args: { limit: 30 },
  },
  {
    id: "szse-home",
    label: "深交所市场概况与最新公告",
    sourceGroup: "filings",
    site: "szse",
    command: "home",
    args: { limit: 30 },
  },
  {
    id: "bse-announcements",
    label: "北交所官方公告",
    sourceGroup: "filings",
    site: "bse",
    command: "announcement",
    args: { limit: 30 },
  },
  {
    id: "cninfo-pdf",
    label: "巨潮资讯公告 PDF",
    sourceGroup: "filings",
    site: "cninfo",
    command: "disclosure-pdf",
    args: { market: "沪深京", limit: 30 },
  },
  {
    id: "macro-flash",
    label: "金十数据宏观快讯",
    sourceGroup: "macro",
    site: "jin10",
    command: "kuaixun",
    args: { limit: 30 },
  },
  {
    id: "macro-news",
    label: "新浪财经宏观新闻",
    sourceGroup: "macro",
    site: "sinafinance",
    command: "news",
    args: { type: 2, limit: 30 },
  },
  {
    id: "breaking-news",
    label: "财联社实时电报",
    sourceGroup: "news",
    site: "cls",
    command: "telegraph",
    args: { limit: 30 },
  },
  {
    id: "finance-news",
    label: "新浪财经新闻",
    sourceGroup: "news",
    site: "sinafinance",
    command: "news",
    args: { type: 1, limit: 30 },
  },
  {
    id: "xueqiu-hot",
    label: "雪球人气个股热度榜",
    sourceGroup: "social",
    site: "xueqiu",
    command: "hot-stocks",
    args: { limit: 30 },
  },
]

export const OPENCLI_SITUATION_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "situation-breaking-news",
    label: "实时事件 · 财联社",
    sourceGroup: "realtime-event",
    site: "cls",
    command: "telegraph",
    args: { limit: 30 },
  },
  {
    id: "situation-finance-news",
    label: "新闻证据 · 新浪财经",
    sourceGroup: "news-evidence",
    site: "sinafinance",
    command: "news",
    args: { limit: 30 },
  },
  {
    id: "bilibili-discovery",
    label: "视频发现 · Bilibili",
    sourceGroup: "video-discovery",
    site: "bilibili",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股 市场"],
  },
  {
    id: "douyin-discovery",
    label: "短视频发现 · 抖音",
    sourceGroup: "video-discovery",
    site: "douyin",
    command: "search",
    args: { query: "A股 市场", limit: 20 },
  },
  {
    id: "bilibili-transcript",
    label: "视频字幕证据 · Bilibili",
    sourceGroup: "video-transcript",
    site: "bilibili",
    command: "subtitle",
    args: {},
    positionalArgs: ["BV1gDKB65EJA"],
  },
  {
    id: "youtube-discovery",
    label: "国际视频发现 · YouTube",
    sourceGroup: "video-discovery",
    site: "youtube",
    command: "search",
    args: { limit: 10, upload: "week" },
    positionalArgs: ["A股 market China stocks"],
  },
]

type OpenCLIBusinessWorkflowOptions = {
  workflowId: string
  cadence: string
  sources: OpenCLISourceSlot[]
  sourceLabel: string
  sourceDescription: string
  recordsLabel: string
  maxItemsPerRun: number
  allowedDomains: string[]
}

function catalogItem(id: string): WorkflowNodeCatalogItem {
  const item = WORKFLOW_NODE_CATALOG.find((entry) => entry.id === id)
  if (!item) throw new Error(`[opencli-business-workflows] catalog item missing: ${id}`)
  return item
}

function configureSourcePackage(
  id: string,
  position: { x: number; y: number },
  options: OpenCLIBusinessWorkflowOptions,
): WorkflowProjectNode {
  const node = createWorkflowNodeFromCatalog(catalogItem("package.opencli.multi-source-hda"), id, position)
  return {
    ...node,
    params: {
      ...node.params,
      runtime: "iii",
      exposeRawSourceItems: true,
      sources: options.sources,
      execution: { fanout: "parallel", failureMode: "collect-per-source" },
      outputContract: {
        items: "items[]",
        evidence: "source lineage + run trace + adapter task id",
        health: "per-source completed/empty/failed",
      },
      aiCallable: {
        schema: "opencli.multi_source_hda.v1",
        editable: ["sources", "sources[].args", "sources[].positionalArgs"],
        sourceMode: "parallel",
      },
    },
    topicCollapse: {
      groupId: `${id}-package`,
      nodeCount: options.sources.length + 1,
      mode: "locked",
      packageInternal: true,
    },
    internals: buildOpenCLIMultiSourceHDAInternals(options.sources, { exposeRawSourceItems: true }),
    ui: {
      ...node.ui,
      label: options.sourceLabel,
      description: options.sourceDescription,
    },
  }
}

function buildOpenCLIBusinessWorkflow(name: string, options: OpenCLIBusinessWorkflowOptions) {
  const schedule = createWorkflowNodeFromCatalog(catalogItem("intelligence.schedule.cron"), `${options.workflowId}-schedule`, { x: 70, y: 240 })
  schedule.params = { ...schedule.params, interval: options.cadence, timezone: "Asia/Shanghai" }
  schedule.ui = { ...schedule.ui, label: "采集调度", description: `${options.cadence} 触发，也支持手动测试运行` }

  const sourcePackage = configureSourcePackage(`${options.workflowId}-sources`, { x: 370, y: 190 }, options)
  const hygiene = createWorkflowNodeFromCatalog(catalogItem("package.processing.record-hygiene"), `${options.workflowId}-hygiene`, { x: 760, y: 190 })
  hygiene.params = {
    ...hygiene.params,
    outputContract: { records: "record.v1[]", rejected: "rejection[]", metrics: "hygieneMetrics" },
  }
  hygiene.ui = { ...hygiene.ui, label: "记录清洗与准入", description: "输入 items；输出 records、rejected、metrics，全部保留来源血缘" }

  const records = createWorkflowNodeFromCatalog(catalogItem("intelligence.sink.records"), `${options.workflowId}-records`, { x: 1120, y: 100 })
  records.ui = { ...records.ui, label: options.recordsLabel, description: "写入数据工作台；输出 stored、rejected、metrics 与 run trace 引用" }

  const nodes: WorkflowProjectNode[] = [schedule, sourcePackage, hygiene, records]
  const edges = [
    { id: `${schedule.id}-${sourcePackage.id}`, source: schedule.id, target: sourcePackage.id, sourcePort: "tick", targetPort: "in" },
    { id: `${sourcePackage.id}-${hygiene.id}`, source: sourcePackage.id, target: hygiene.id, sourcePort: "out", targetPort: "in" },
    { id: `${hygiene.id}-${records.id}`, source: hygiene.id, target: records.id, sourcePort: "out", targetPort: "records" },
  ]

  return parseWorkflowProject({
    ...PACKAGED_WORKFLOW_PROJECT,
    id: `draft-${options.workflowId}-${Date.now()}`,
    name,
    nodes,
    edges,
    adapters: opencliAdaptersForSourceSlots(options.sources),
    settings: {
      ...PACKAGED_WORKFLOW_PROJECT.settings,
      timezone: "Asia/Shanghai",
      deterministicSimulation: false,
      maxItemsPerRun: options.maxItemsPerRun,
    },
    agentPermissions: {
      ...PACKAGED_WORKFLOW_PROJECT.agentPermissions,
      canFetchNetwork: true,
      canWriteInbox: true,
      canSendNotifications: false,
      allowedDomains: options.allowedDomains,
    },
  })
}

export function buildAshareMarketWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "ashare-market-intelligence",
    cadence: "5m",
    sources: ASHARE_OPENCLI_SOURCES,
    sourceLabel: "A 股消息与数据来源",
    sourceDescription: "行情、公告与 PDF、宏观、新闻、社交五类来源并行采集；逐来源显示完成、空结果或失败",
    recordsLabel: "A 股金融数据集",
    maxItemsPerRun: 1_000,
    allowedDomains: [
      "eastmoney.com",
      "10jqka.com.cn",
      "tdx.com.cn",
      "xueqiu.com",
      "cninfo.com.cn",
      "sse.com.cn",
      "szse.cn",
      "bse.cn",
      "jin10.com",
      "cls.cn",
      "sina.com.cn",
    ],
  })
}

export function buildOpenCLISituationAwarenessWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "opencli-situation-awareness",
    cadence: "5m",
    sources: OPENCLI_SITUATION_SOURCES,
    sourceLabel: "实时 / 新闻 / 视频证据采集",
    sourceDescription: "并行采集实时事件、新闻、视频目录与字幕；在运行痕迹中公开来源、时间和采集证据",
    recordsLabel: "态势证据数据集",
    maxItemsPerRun: 300,
    allowedDomains: ["cls.cn", "sina.com.cn", "bilibili.com", "douyin.com", "youtube.com"],
  })
}
