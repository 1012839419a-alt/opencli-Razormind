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
    reason: "命令已注册，但真实请求为空；不放进默认工作流。",
  },
  {
    site: "cninfo",
    command: "disclosure",
    status: "degraded",
    reason: "当前返回空字段或空结果；先由交易所官方披露和东方财富公告补齐，不写入脏记录。",
  },
  {
    site: "bse",
    command: "announcement",
    status: "degraded",
    reason: "公告命令真实请求为空；默认改用可返回数据的北交所问询函。",
  },
  {
    site: "mof",
    command: "announcement",
    status: "degraded",
    reason: "当前上游返回 HTTP 404；不生成默认可运行节点。",
  },
  {
    site: "safe",
    command: "announcement",
    status: "degraded",
    reason: "当前上游返回 HTTP 404；不生成默认可运行节点。",
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
    id: "core-index-quotes",
    label: "A 股核心指数实时行情",
    sourceGroup: "market",
    site: "eastmoney",
    command: "index-quote",
    args: {},
  },
  {
    id: "sector-breadth",
    label: "A 股行业与概念板块强弱",
    sourceGroup: "market",
    site: "eastmoney",
    command: "sectors",
    args: { limit: 30 },
  },
  {
    id: "main-fund-flow",
    label: "A 股主力资金流向",
    sourceGroup: "market",
    site: "eastmoney",
    command: "money-flow",
    args: { limit: 50 },
  },
  {
    id: "limit-moves",
    label: "A 股涨跌停事件",
    sourceGroup: "market",
    site: "eastmoney",
    command: "limit-up",
    args: { limit: 50 },
  },
  {
    id: "dragon-tiger-list",
    label: "沪深京龙虎榜",
    sourceGroup: "market",
    site: "eastmoney",
    command: "longhu",
    args: { limit: 50 },
  },
  {
    id: "margin-balance",
    label: "A 股融资融券余额",
    sourceGroup: "market",
    site: "eastmoney",
    command: "rzrq",
    args: { limit: 30 },
  },
  {
    id: "valuation-snapshot",
    label: "A 股估值横截面",
    sourceGroup: "market",
    site: "eastmoney",
    command: "valuation",
    args: { limit: 50 },
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
    id: "earnings-forecast",
    label: "沪深京上市公司业绩预告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "yjyg",
    args: { limit: 50 },
  },
  {
    id: "announcements",
    label: "东方财富沪深京上市公司公告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "notices",
    args: { market: "all", limit: 100 },
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
    id: "szse-inquiries",
    label: "深交所问询函与回复",
    sourceGroup: "filings",
    site: "szse",
    command: "inquiry",
    args: { limit: 30 },
  },
  {
    id: "bse-inquiries",
    label: "北交所问询函与回复",
    sourceGroup: "filings",
    site: "bse",
    command: "inquiry",
    args: { limit: 30 },
  },
  {
    id: "csrc-announcements",
    label: "证监会监管公告",
    sourceGroup: "macro",
    site: "csrc",
    command: "announcement",
    args: { limit: 30 },
  },
  {
    id: "pboc-credit",
    label: "人民银行人民币信贷数据",
    sourceGroup: "macro",
    site: "pboc",
    command: "credit",
    args: { limit: 12 },
  },
  {
    id: "pboc-lpr",
    label: "人民银行 LPR",
    sourceGroup: "macro",
    site: "pboc",
    command: "lpr",
    args: { limit: 12 },
  },
  {
    id: "nbs-release-calendar",
    label: "国家统计局数据发布日程",
    sourceGroup: "macro",
    site: "statsgov",
    command: "nbs",
    args: { limit: 20 },
  },
  {
    id: "nbs-monthly-data",
    label: "国家统计局月度指标",
    sourceGroup: "macro",
    site: "statsgov",
    command: "monthly-data",
    args: { type: "month", limit: 10 },
  },
  {
    id: "shibor",
    label: "上海银行间同业拆借利率",
    sourceGroup: "macro",
    site: "eastmoney",
    command: "shibor",
    args: { limit: 20 },
  },
  {
    id: "macro-cpi-crosscheck",
    label: "东方财富中国 CPI 交叉校验",
    sourceGroup: "macro",
    site: "eastmoney",
    command: "macro-data",
    args: { type: "cpi", limit: 12 },
  },
  {
    id: "money-supply",
    label: "中国货币供应量 M0/M1/M2",
    sourceGroup: "macro",
    site: "eastmoney",
    command: "moneysupply",
    args: { limit: 12 },
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
    id: "eastmoney-breaking-news",
    label: "东方财富 7×24 快讯",
    sourceGroup: "news",
    site: "eastmoney",
    command: "kuaixun",
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
    id: "macro-news",
    label: "新浪财经宏观新闻",
    sourceGroup: "news",
    site: "sinafinance",
    command: "news",
    args: { type: 2, limit: 30 },
  },
  {
    id: "cs-news",
    label: "中国证券报市场资讯",
    sourceGroup: "news",
    site: "cs",
    command: "kuaixun",
    args: { limit: 30 },
  },
  {
    id: "xueqiu-stock-social",
    label: "雪球 A 股七日社交热度",
    sourceGroup: "social",
    site: "xueqiu",
    command: "stock-social",
    args: { order: "follow7d", limit: 30 },
  },
]

export const ASHARE_STOCK_RESEARCH_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "stock-quote",
    label: "个股实时行情 · 贵州茅台",
    sourceGroup: "price",
    site: "eastmoney",
    command: "quote",
    args: {},
    positionalArgs: ["600519"],
  },
  {
    id: "stock-kline",
    label: "个股日线与复权行情",
    sourceGroup: "price",
    site: "eastmoney",
    command: "kline",
    args: { period: "day", adjust: "forward", limit: 60 },
    positionalArgs: ["600519"],
  },
  {
    id: "stock-fund-flow",
    label: "个股五日资金流向",
    sourceGroup: "capital",
    site: "eastmoney",
    command: "stock-flow",
    args: { code: "600519", market: "sh" },
  },
  {
    id: "stock-financials",
    label: "个股财务摘要",
    sourceGroup: "fundamental",
    site: "eastmoney",
    command: "bbsj-summary",
    args: { code: "600519", limit: 12 },
  },
  {
    id: "stock-announcements",
    label: "个股公司公告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "announcement",
    args: { code: "600519", limit: 50 },
  },
  {
    id: "stock-research-reports",
    label: "个股券商研报",
    sourceGroup: "research",
    site: "eastmoney",
    command: "research",
    args: { code: "600519", type: "stock", limit: 20 },
  },
  {
    id: "stock-general-meeting",
    label: "个股股东大会日程",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "general-meeting",
    args: { code: "600519", limit: 20 },
  },
  {
    id: "stock-dividend",
    label: "个股分红送配",
    sourceGroup: "fundamental",
    site: "eastmoney",
    command: "dividend",
    args: { code: "600519", limit: 10 },
  },
  {
    id: "stock-national-hold",
    label: "国家队、险资、公募与 QFII 持仓",
    sourceGroup: "ownership",
    site: "eastmoney",
    command: "national-hold",
    args: { code: "600519", limit: 20 },
  },
  {
    id: "stock-top-holders",
    label: "个股十大流通股东",
    sourceGroup: "ownership",
    site: "eastmoney",
    command: "holders",
    args: { limit: 20 },
    positionalArgs: ["600519"],
  },
  {
    id: "stock-holder-count",
    label: "个股股东户数与筹码集中度",
    sourceGroup: "ownership",
    site: "eastmoney",
    command: "holder_num",
    args: { limit: 20 },
    positionalArgs: ["600519"],
  },
  {
    id: "stock-guba",
    label: "东方财富股吧讨论",
    sourceGroup: "community",
    site: "eastmoney",
    command: "guba",
    args: { code: "600519", limit: 30, sortType: "1" },
  },
  {
    id: "stock-xueqiu-comments",
    label: "雪球个股讨论",
    sourceGroup: "community",
    site: "xueqiu",
    command: "comments",
    args: { limit: 30 },
    positionalArgs: ["SH600519"],
  },
]

export const ASHARE_THEME_RADAR_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "theme-concept-board",
    label: "东方财富概念板块排行",
    sourceGroup: "theme",
    site: "eastmoney",
    command: "concept-board",
    args: { sort: "turnover", limit: 50 },
  },
  {
    id: "theme-sector-breadth",
    label: "东方财富行业与概念强弱",
    sourceGroup: "theme",
    site: "eastmoney",
    command: "sectors",
    args: { limit: 50 },
  },
  {
    id: "theme-market-money-flow",
    label: "东方财富主力资金排行",
    sourceGroup: "capital",
    site: "eastmoney",
    command: "money-flow",
    args: { limit: 50 },
  },
  {
    id: "theme-industry-flow",
    label: "东方财富板块资金流",
    sourceGroup: "capital",
    site: "eastmoney",
    command: "sector-flow",
    args: { limit: 50 },
  },
  {
    id: "theme-strong-stocks",
    label: "同花顺强势股题材归因",
    sourceGroup: "signal",
    site: "ths",
    command: "hot",
    args: { limit: 50 },
  },
  {
    id: "theme-tdx-hot-rank",
    label: "通达信股票热度排行",
    sourceGroup: "signal",
    site: "tdx",
    command: "hot-rank",
    args: { limit: 30 },
  },
  {
    id: "theme-cls-news",
    label: "财联社实时题材事件",
    sourceGroup: "news",
    site: "cls",
    command: "telegraph",
    args: { limit: 30 },
  },
  {
    id: "theme-eastmoney-news",
    label: "东方财富 7×24 快讯",
    sourceGroup: "news",
    site: "eastmoney",
    command: "kuaixun",
    args: { limit: 30 },
  },
]

export const ASHARE_DISCLOSURE_RISK_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "risk-market-announcements",
    label: "沪深京公司公告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "notices",
    args: { market: "all", limit: 100 },
  },
  {
    id: "risk-earnings-forecast",
    label: "沪深京业绩预告",
    sourceGroup: "filings",
    site: "eastmoney",
    command: "yjyg",
    args: { limit: 50 },
  },
  {
    id: "risk-executive-holding",
    label: "上市公司高管持股变动",
    sourceGroup: "ownership-risk",
    site: "eastmoney",
    command: "executive-hold",
    args: { limit: 50 },
  },
  {
    id: "risk-equity-pledge",
    label: "上市公司股权质押",
    sourceGroup: "ownership-risk",
    site: "eastmoney",
    command: "pledge",
    args: { limit: 50 },
  },
  {
    id: "risk-sse-announcements",
    label: "上交所官方公告",
    sourceGroup: "exchange",
    site: "sse",
    command: "announcements",
    args: { limit: 30 },
  },
  {
    id: "risk-szse-announcements",
    label: "深交所最新公告",
    sourceGroup: "exchange",
    site: "szse",
    command: "home",
    args: { limit: 30 },
  },
  {
    id: "risk-szse-inquiries",
    label: "深交所问询函",
    sourceGroup: "inquiry",
    site: "szse",
    command: "inquiry",
    args: { limit: 30 },
  },
  {
    id: "risk-bse-inquiries",
    label: "北交所问询函",
    sourceGroup: "inquiry",
    site: "bse",
    command: "inquiry",
    args: { limit: 30 },
  },
  {
    id: "risk-csrc-announcements",
    label: "证监会监管公告",
    sourceGroup: "regulator",
    site: "csrc",
    command: "announcement",
    args: { limit: 30 },
  },
  {
    id: "risk-breaking-news",
    label: "财联社风险事件快讯",
    sourceGroup: "news",
    site: "cls",
    command: "telegraph",
    args: { limit: 30 },
  },
]

export const ASHARE_SELF_MEDIA_SOURCES: OpenCLISourceSlot[] = [
  {
    id: "media-weixin",
    label: "微信公众号文章搜索",
    sourceGroup: "articles",
    site: "weixin",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股"],
  },
  {
    id: "media-guba",
    label: "东方财富股吧",
    sourceGroup: "community",
    site: "eastmoney",
    command: "guba",
    args: { code: "300059", limit: 30, sortType: "1" },
  },
  {
    id: "media-xueqiu-comments",
    label: "雪球个股讨论 · 默认贵州茅台",
    sourceGroup: "community",
    site: "xueqiu",
    command: "comments",
    args: { limit: 30 },
    positionalArgs: ["SH600519"],
  },
  {
    id: "media-xueqiu-social",
    label: "雪球 A 股社交热度",
    sourceGroup: "community",
    site: "xueqiu",
    command: "stock-social",
    args: { order: "follow7d", limit: 30 },
  },
  {
    id: "media-weibo",
    label: "微博 A 股搜索",
    sourceGroup: "social",
    site: "weibo",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股"],
  },
  {
    id: "media-xiaohongshu",
    label: "小红书 A 股笔记",
    sourceGroup: "social",
    site: "xiaohongshu",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股"],
  },
  {
    id: "media-bilibili",
    label: "B站 A 股视频",
    sourceGroup: "video",
    site: "bilibili",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股"],
  },
  {
    id: "media-douyin",
    label: "抖音 A 股视频",
    sourceGroup: "video",
    site: "douyin",
    command: "search",
    args: { query: "A股", limit: 20 },
  },
  {
    id: "media-zhihu",
    label: "知乎 A 股内容",
    sourceGroup: "knowledge",
    site: "zhihu",
    command: "search",
    args: { limit: 20 },
    positionalArgs: ["A股"],
  },
  {
    id: "media-xueqiu-news",
    label: "雪球资讯与讨论帖",
    sourceGroup: "community",
    site: "xueqiu",
    command: "news",
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
    sourceDescription: "行情资金、财报披露、宏观监管、财经新闻、社交热度五类国内来源并行采集；逐来源显示完成、空结果或失败",
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
      "csrc.gov.cn",
      "pbc.gov.cn",
      "stats.gov.cn",
      "cls.cn",
      "sina.com.cn",
      "cs.com.cn",
    ],
  })
}

export function buildAshareStockResearchWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "ashare-stock-research",
    cadence: "15m",
    sources: ASHARE_STOCK_RESEARCH_SOURCES,
    sourceLabel: "个股全景数据来源 · 默认 600519",
    sourceDescription: "行情、K 线、资金、财务、公告、研报、机构持仓、股吧和雪球讨论并行采集；股票代码可统一替换，股吧和雪球需要对应浏览器登录态",
    recordsLabel: "A 股个股研究数据集",
    maxItemsPerRun: 500,
    allowedDomains: ["eastmoney.com", "10jqka.com.cn", "xueqiu.com"],
  })
}

export function buildAshareThemeRadarWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "ashare-theme-radar",
    cadence: "5m",
    sources: ASHARE_THEME_RADAR_SOURCES,
    sourceLabel: "题材、板块与资金来源",
    sourceDescription: "概念板块、行业资金、强势股归因、股票热度和实时事件并行采集，用于识别正在形成的 A 股主题；通达信热榜需要对应浏览器登录态",
    recordsLabel: "A 股题材信号数据集",
    maxItemsPerRun: 500,
    allowedDomains: ["eastmoney.com", "10jqka.com.cn", "tdx.com.cn", "cls.cn"],
  })
}

export function buildAshareDisclosureRiskWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "ashare-disclosure-risk",
    cadence: "15m",
    sources: ASHARE_DISCLOSURE_RISK_SOURCES,
    sourceLabel: "公告、问询与监管风险来源",
    sourceDescription: "公司公告、业绩预告、高管持股、股权质押、交易所问询、证监会公告和风险快讯并行采集",
    recordsLabel: "A 股公告监管风险数据集",
    maxItemsPerRun: 600,
    allowedDomains: [
      "eastmoney.com",
      "10jqka.com.cn",
      "sse.com.cn",
      "szse.cn",
      "bse.cn",
      "csrc.gov.cn",
      "cls.cn",
    ],
  })
}

export function buildAshareSelfMediaWorkflow(name: string) {
  return buildOpenCLIBusinessWorkflow(name, {
    workflowId: "ashare-self-media-listening",
    cadence: "30m",
    sources: ASHARE_SELF_MEDIA_SOURCES,
    sourceLabel: "A 股自媒体与社区来源",
    sourceDescription: "公众号、股吧、雪球、微博、小红书、B站、抖音和知乎并行采集；需要登录的平台按来源独立显示健康状态",
    recordsLabel: "A 股自媒体舆情数据集",
    maxItemsPerRun: 500,
    allowedDomains: [
      "sogou.com",
      "weixin.qq.com",
      "eastmoney.com",
      "xueqiu.com",
      "weibo.com",
      "xiaohongshu.com",
      "bilibili.com",
      "douyin.com",
      "zhihu.com",
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
