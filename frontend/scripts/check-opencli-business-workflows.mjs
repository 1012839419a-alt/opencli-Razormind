import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const businessSource = await readFile(new URL('../lib/workflow/opencli-business-workflows.ts', import.meta.url), 'utf8')
const catalogSource = await readFile(new URL('../lib/workflow/node-catalog.ts', import.meta.url), 'utf8')
const templateSource = await readFile(new URL('../lib/workflow/studio-templates.ts', import.meta.url), 'utf8')

function parseSources(exportName, nextExportName) {
  const block = businessSource.slice(
    businessSource.indexOf(`export const ${exportName}`),
    businessSource.indexOf(`export const ${nextExportName}`),
  )
  return [...block.matchAll(/^  \{\r?\n([\s\S]*?)^  \},?$/gm)].map(([, body]) => ({
    id: body.match(/id: "([^"]+)"/)?.[1],
    group: body.match(/sourceGroup: "([^"]+)"/)?.[1],
    site: body.match(/site: "([^"]+)"/)?.[1],
    command: body.match(/command: "([^"]+)"/)?.[1],
  }))
}

const ashareSources = parseSources('ASHARE_OPENCLI_SOURCES', 'ASHARE_STOCK_RESEARCH_SOURCES')
const stockSources = parseSources('ASHARE_STOCK_RESEARCH_SOURCES', 'ASHARE_THEME_RADAR_SOURCES')
const themeSources = parseSources('ASHARE_THEME_RADAR_SOURCES', 'ASHARE_DISCLOSURE_RISK_SOURCES')
const riskSources = parseSources('ASHARE_DISCLOSURE_RISK_SOURCES', 'ASHARE_SELF_MEDIA_SOURCES')
const mediaSources = parseSources('ASHARE_SELF_MEDIA_SOURCES', 'OPENCLI_SITUATION_SOURCES')

test('registers five A-share collection tools and the situation workflow', () => {
  for (const [templateId, builder] of [
    ['ashare-market-intelligence', 'buildAshareMarketWorkflow'],
    ['ashare-stock-research', 'buildAshareStockResearchWorkflow'],
    ['ashare-theme-radar', 'buildAshareThemeRadarWorkflow'],
    ['ashare-disclosure-risk', 'buildAshareDisclosureRiskWorkflow'],
    ['ashare-self-media-listening', 'buildAshareSelfMediaWorkflow'],
    ['opencli-situation-awareness', 'buildOpenCLISituationAwarenessWorkflow'],
  ]) {
    assert.match(
      templateSource,
      new RegExp(`if \\(template === '${templateId}'\\) return ${builder}\\(name\\)`),
    )
  }
  assert.match(templateSource, /id: 'opencli-situation-awareness'/)
})

test('domestic OODA workflow covers five source groups without fixtures', () => {
  assert.equal(ashareSources.length, 32)
  assert.equal(new Set(ashareSources.map(({ id }) => id)).size, 32)
  assert.deepEqual(
    Object.fromEntries(
      ['market', 'filings', 'macro', 'news', 'social'].map((group) => [
        group,
        ashareSources.filter((source) => source.group === group).length,
      ]),
    ),
    { market: 11, filings: 7, macro: 8, news: 5, social: 1 },
  )
  assert.deepEqual(
    ashareSources.map(({ id, group, site, command }) => `${id}|${group}|${site}|${command}`),
    [
      'market-breadth|market|eastmoney|gridlist',
      'watchlist-quotes|market|eastmoney|quote',
      'core-index-quotes|market|eastmoney|index-quote',
      'sector-breadth|market|eastmoney|sectors',
      'main-fund-flow|market|eastmoney|money-flow',
      'limit-moves|market|eastmoney|limit-up',
      'dragon-tiger-list|market|eastmoney|longhu',
      'margin-balance|market|eastmoney|rzrq',
      'valuation-snapshot|market|eastmoney|valuation',
      'ths-hot|market|ths|hot',
      'tdx-hot-rank|market|tdx|hot-rank',
      'fundamentals|filings|eastmoney|bbsj-summary',
      'earnings-forecast|filings|eastmoney|yjyg',
      'announcements|filings|eastmoney|notices',
      'sse-announcements|filings|sse|announcements',
      'szse-home|filings|szse|home',
      'szse-inquiries|filings|szse|inquiry',
      'bse-inquiries|filings|bse|inquiry',
      'csrc-announcements|macro|csrc|announcement',
      'pboc-credit|macro|pboc|credit',
      'pboc-lpr|macro|pboc|lpr',
      'nbs-release-calendar|macro|statsgov|nbs',
      'nbs-monthly-data|macro|statsgov|monthly-data',
      'shibor|macro|eastmoney|shibor',
      'macro-cpi-crosscheck|macro|eastmoney|macro-data',
      'money-supply|macro|eastmoney|moneysupply',
      'breaking-news|news|cls|telegraph',
      'eastmoney-breaking-news|news|eastmoney|kuaixun',
      'finance-news|news|sinafinance|news',
      'macro-news|news|sinafinance|news',
      'cs-news|news|cs|kuaixun',
      'xueqiu-stock-social|social|xueqiu|stock-social',
    ],
  )
  assert.doesNotMatch(businessSource, /runtime:\s*"fixture"|mode:\s*"fixture"/)
  assert.match(businessSource, /deterministicSimulation: false/)
  assert.match(businessSource, /exposeRawSourceItems: true/)
  assert.match(businessSource, /nodeCount: options\.sources\.length \+ 1/)
  assert.match(businessSource, /maxItemsPerRun: 1_000/)
})

test('A-share focused templates lock their source counts and command pairings', () => {
  for (const [sources, count] of [
    [stockSources, 13],
    [themeSources, 8],
    [riskSources, 10],
    [mediaSources, 10],
  ]) {
    assert.equal(sources.length, count)
    assert.equal(new Set(sources.map(({ id }) => id)).size, count)
  }
  assert.deepEqual(
    stockSources.map(({ site, command }) => `${site}/${command}`),
    [
      'eastmoney/quote',
      'eastmoney/kline',
      'eastmoney/stock-flow',
      'eastmoney/bbsj-summary',
      'eastmoney/announcement',
      'eastmoney/research',
      'eastmoney/general-meeting',
      'eastmoney/dividend',
      'eastmoney/national-hold',
      'eastmoney/holders',
      'eastmoney/holder_num',
      'eastmoney/guba',
      'xueqiu/comments',
    ],
  )
  assert.deepEqual(
    themeSources.map(({ site, command }) => `${site}/${command}`),
    [
      'eastmoney/concept-board',
      'eastmoney/sectors',
      'eastmoney/money-flow',
      'eastmoney/sector-flow',
      'ths/hot',
      'tdx/hot-rank',
      'cls/telegraph',
      'eastmoney/kuaixun',
    ],
  )
  assert.deepEqual(
    riskSources.map(({ site, command }) => `${site}/${command}`),
    [
      'eastmoney/notices',
      'eastmoney/yjyg',
      'eastmoney/executive-hold',
      'eastmoney/pledge',
      'sse/announcements',
      'szse/home',
      'szse/inquiry',
      'bse/inquiry',
      'csrc/announcement',
      'cls/telegraph',
    ],
  )
  assert.deepEqual(
    mediaSources.map(({ site, command }) => `${site}/${command}`),
    [
      'weixin/search',
      'eastmoney/guba',
      'xueqiu/comments',
      'xueqiu/stock-social',
      'weibo/search',
      'xiaohongshu/search',
      'bilibili/search',
      'douyin/search',
      'zhihu/search',
      'xueqiu/news',
    ],
  )
  assert.match(
    businessSource,
    /buildAshareStockResearchWorkflow\(name: string\)[\s\S]*?sources: ASHARE_STOCK_RESEARCH_SOURCES,/,
  )
  assert.match(
    businessSource,
    /buildAshareThemeRadarWorkflow\(name: string\)[\s\S]*?sources: ASHARE_THEME_RADAR_SOURCES,/,
  )
  assert.match(
    businessSource,
    /buildAshareDisclosureRiskWorkflow\(name: string\)[\s\S]*?sources: ASHARE_DISCLOSURE_RISK_SOURCES,/,
  )
  assert.match(
    businessSource,
    /buildAshareSelfMediaWorkflow\(name: string\)[\s\S]*?sources: ASHARE_SELF_MEDIA_SOURCES,/,
  )
  assert.match(businessSource, /args: \{ period: "day", adjust: "forward", limit: 60 \}/)
  assert.match(businessSource, /args: \{ code: "600519", market: "sh" \}/)
  assert.match(businessSource, /args: \{ sort: "turnover", limit: 50 \}/)
  assert.match(businessSource, /args: \{ market: "all", limit: 100 \}/)
  assert.match(businessSource, /positionalArgs: \["SH600519"\]/)
  assert.match(businessSource, /positionalArgs: \["A股"\]/)
  assert.match(businessSource, /股吧和雪球需要对应浏览器登录态/)
  assert.match(businessSource, /通达信热榜需要对应浏览器登录态/)
})

test('known domestic source gaps stay explicit instead of becoming fake runnable nodes', () => {
  assert.match(businessSource, /site: "gelonghui"[\s\S]*status: "unavailable"/)
  assert.match(businessSource, /site: "jin10"[\s\S]*status: "degraded"/)
  assert.match(businessSource, /site: "cninfo"[\s\S]*status: "degraded"/)
  assert.match(businessSource, /site: "mof"[\s\S]*status: "degraded"/)
  assert.match(businessSource, /site: "safe"[\s\S]*status: "degraded"/)
  assert.match(businessSource, /不生成伪节点/)
  assert.match(businessSource, /不写入脏记录/)
})

test('situation workflow collects cross-platform discovery and stable transcript evidence', () => {
  assert.match(businessSource, /site: "bilibili"[\s\S]*command: "subtitle"/)
  assert.match(businessSource, /site: "youtube"[\s\S]*command: "search"/)
  assert.match(businessSource, /公开来源、时间和采集证据/)
  assert.match(businessSource, /sourceGroup: "video-transcript"/)
})

test('OpenCLI source slots preserve positional command arguments', () => {
  assert.match(catalogSource, /positionalArgs\?: string\[\]/)
  assert.match(catalogSource, /source\.positionalArgs \? \{ positionalArgs: source\.positionalArgs \}/)
  assert.match(catalogSource, /sourceBindingId\?: string/)
  assert.match(catalogSource, /sourceBindingRevisionId\?: string/)
  assert.match(catalogSource, /sourceBindingRevisionNumber\?: number/)
  assert.match(catalogSource, /Number\.isInteger\(slot\.sourceBindingRevisionNumber\)/)
  assert.match(catalogSource, /source\.sourceBindingRevisionId \? \{ sourceBindingRevisionId: source\.sourceBindingRevisionId \}/)
  assert.match(businessSource, /positionalArgs: \["600519,000001,300750"\]/)
  assert.match(businessSource, /positionalArgs: \["SH600519"\]/)
  assert.match(businessSource, /positionalArgs: \["A股"\]/)
  assert.match(businessSource, /editable: \["sources", "sources\[\]\.args", "sources\[\]\.positionalArgs"\]/)
})

test('workflow surfaces explicit outputs and source health semantics', () => {
  assert.match(businessSource, /items: "items\[\]"/)
  assert.match(businessSource, /health: "per-source completed\/empty\/failed"/)
  assert.match(businessSource, /records: "record\.v1\[\]", rejected: "rejection\[\]", metrics: "hygieneMetrics"/)
  assert.match(businessSource, /输出 stored、rejected、metrics 与 run trace 引用/)
})
