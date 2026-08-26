import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('Next View Transition integration is enabled and stays locally opt-in', async () => {
  const [config, localTransition, shell, routeTransition] = await Promise.all([
    read('next.config.mjs'),
    read('components/motion/local-view-transition.tsx'),
    read('components/shell/app-shell.tsx'),
    read('components/motion/app-route-transition.tsx'),
  ])

  assert.match(config, /viewTransition:\s*VIEW_TRANSITIONS_ENABLED/)
  assert.match(localTransition, /<ViewTransition name=\{name\}>/)
  assert.doesNotMatch(shell, /<ViewTransition\b/)
  assert.doesNotMatch(routeTransition, /<ViewTransition\b/)
})

test('persistent application chrome stays outside the routed animation boundary', async () => {
  const shell = await read('components/shell/app-shell.tsx')
  const sidebarIndex = shell.indexOf('<AppSidebar />')
  const headerIndex = shell.indexOf('<AppHeader')
  const transitionIndex = shell.indexOf('<AppRouteTransition>')

  assert.ok(sidebarIndex >= 0, 'AppSidebar should remain mounted')
  assert.ok(headerIndex >= 0, 'AppHeader should remain mounted')
  assert.ok(transitionIndex > sidebarIndex, 'route animation must not wrap the sidebar')
  assert.ok(transitionIndex > headerIndex, 'route animation must not wrap the header')
  assert.match(shell, /<AppRouteTransition>\{children\}<\/AppRouteTransition>/)
  assert.match(shell, /className="[^"]*relative[^"]*z-0[^"]*overflow-x-clip[^"]*bg-background[^"]*"/)
})

test('sidebar keeps automation separate from Agent surfaces', async () => {
  const [navigation, sidebar] = await Promise.all([
    read('lib/navigation.ts'),
    read('components/shell/app-sidebar.tsx'),
  ])

  for (const label of [
    '概览',
    '任务与通知',
    '项目',
    '插件中心',
    '自动化',
    '执行资源',
    '成果与数据',
    '模型与连接',
  ]) {
    assert.match(navigation, new RegExp(`label: '${label}'`))
  }

  assert.match(navigation, /href: '\/inbox'/)
  assert.match(navigation, /match: \['\/inbox', '\/tasks', '\/notifications'\]/)
  assert.match(navigation, /match: \['\/schedules'\]/)
  assert.doesNotMatch(navigation, /label: '自动化与 Agent'/)
  assert.doesNotMatch(navigation, /match: \[[^\]]*'\/agents'/)
  assert.doesNotMatch(navigation, /match: \[[^\]]*'\/skills'/)
  assert.match(navigation, /'\/operations-agents': 'Agent 管理'/)
  assert.match(navigation, /match: \['\/nodes', '\/workers'\]/)
  assert.match(navigation, /match: \['\/providers', '\/control\/actions'\]/)
  for (const group of ['工作台', '构建', '运行与数据', '管理']) {
    assert.match(navigation, new RegExp(`label: '${group}'`))
  }
  assert.doesNotMatch(navigation, /label: '工作项'/)
  assert.doesNotMatch(navigation, /label: 'Agent 团队'/)
  assert.doesNotMatch(navigation, /CREATE_WORK_ITEM/)
  assert.doesNotMatch(sidebar, /CREATE_WORK_ITEM/)
  assert.doesNotMatch(sidebar, /新建工作/)
})

test('records use a scalable source-to-table explorer with pagination and raw evidence detail', async () => {
  const records = await read('app/(app)/records/page.tsx')

  assert.match(records, /lg:grid-cols-\[15rem_minmax\(0,1fr\)\]/)
  assert.doesNotMatch(records, /grid min-h-\[38rem\] overflow-hidden/)
  assert.match(records, /min-h-\[20rem\]/)
  assert.match(records, /min-h-\[32rem\]/)
  assert.match(records, /aria-label="成果数据集"/)
  assert.match(records, /useSources\(\{ page: 1, limit: 100 \}\)/)
  assert.match(records, /limit: PAGE_SIZE/)
  assert.match(records, /visibleFields/)
  assert.match(records, /第 \{page\.toLocaleString/)
  assert.match(records, /<Sheet open=\{Boolean\(selectedRecord\)\}/)
  assert.match(records, /标准化数据/)
  assert.match(records, /原始数据/)
})

test('task and automation sibling routes share their consolidated route tabs', async () => {
  const [tabs, inbox, tasks, notifications, sources, schedules, agents, skills] = await Promise.all([
    read('components/shell/route-tabs.tsx'),
    read('app/(app)/inbox/page.tsx'),
    read('app/(app)/tasks/page.tsx'),
    read('app/(app)/notifications/page.tsx'),
    read('app/(app)/sources/page.tsx'),
    read('app/(app)/schedules/page.tsx'),
    read('app/(app)/agents/page.tsx'),
    read('app/(app)/skills/page.tsx'),
  ])

  for (const label of ['待处理', '工作项', '通知规则', '调度', 'Agent', '技能']) {
    assert.match(tabs, new RegExp(`label: '${label}'`))
  }
  for (const page of [inbox, tasks, notifications]) {
    assert.match(page, /ACTION_CENTER_TABS/)
  }
  for (const page of [sources, schedules, agents, skills]) {
    assert.match(page, /AUTOMATION_TABS/)
  }
})

test('studio keeps Agent conversation global while management has its own entry', async () => {
  const [studio, templates, shell, header, agentBubble, agentDock, transition] = await Promise.all([
    read('app/(app)/studio/page.tsx'),
    read('app/(app)/studio/templates/page.tsx'),
    read('components/shell/app-shell.tsx'),
    read('components/shell/app-header.tsx'),
    read('components/shell/global-agent-bubble.tsx'),
    read('components/shell/global-agent-dock.tsx'),
    read('components/motion/app-route-transition.tsx'),
  ])

  assert.match(studio, /\/studio\/templates\?workspace=/)
  assert.match(studio, /创建空白工作流/)
  assert.match(studio, /setCreateTemplate\('blank'\)/)
  assert.doesNotMatch(studio, /Collection starters/i)
  assert.doesNotMatch(studio, /从采集项目开始/)
  assert.doesNotMatch(studio, /FEATURED_COLLECTION_TEMPLATES/)
  assert.doesNotMatch(studio, /与 Agent 创建/)
  assert.doesNotMatch(studio, /\/studio\/new\?workspace=/)
  assert.match(templates, /搜索模板、节点或用途/)
  assert.match(templates, /可复用的执行链路/)
  assert.doesNotMatch(templates, /改用 Agent 创建/)
  assert.match(shell, /<GlobalAgentBubble onClick=\{\(\) => setAgentOpen\(true\)\} \/>/)
  assert.match(shell, /<GlobalAgentDock open=\{agentOpen\}/)
  assert.match(header, /href="\/operations-agents"/)
  assert.doesNotMatch(header, /onOpenAgent/)
  assert.match(agentBubble, /fixed bottom-4 right-4/)
  assert.match(agentBubble, /aria-label="打开全局 Agent"/)
  assert.match(agentDock, /当前上下文/)
  assert.match(agentDock, /new URLSearchParams\(window\.location\.search\)/)
  assert.match(agentDock, /workspace_id: workspaceId/)
  assert.match(agentDock, /const workspaceId = searchParams\.get\('workspace'\)/)
  assert.match(agentDock, /projectId = searchParams\.get\('project'\)/)
  assert.match(agentDock, /workflowId = searchParams\.get\('workflow'\)/)
  assert.match(agentDock, /sourceId = searchParams\.get\('source'\)/)
  assert.match(agentDock, /project_id: projectId/)
  assert.match(agentDock, /workflow_id: workflowId/)
  assert.match(agentDock, /source_id: sourceId/)
  assert.match(agentDock, /work_item_id\?: string \| null/)
  assert.match(agentDock, /workspace_id\?: string \| null/)
  assert.match(agentDock, /proposal_version\?: string \| null/)
  assert.match(agentDock, /apiClient\.post\('\/chat\/confirm', \{ proposal \}\)/)
  assert.match(agentDock, /status === 409/)
  assert.match(agentDock, /仅在后端能解析出唯一授权范围时允许确认写操作/)
  assert.match(agentDock, /\/chat\/confirm/)
  assert.match(agentDock, /queryClient\.invalidateQueries/)
  assert.match(transition, /'\/operations-agents'/)
})

test('SSGOI boundary is pathname-keyed, interruptible, and reduced-motion safe', async () => {
  const transition = await read('components/motion/app-route-transition.tsx')

  assert.match(transition, /const pathname = usePathname\(\)/)
  assert.match(transition, /key=\{pathname\}/)
  assert.match(transition, /data-ssgoi-transition=\{pathname\}/)
  assert.match(transition, /className="[^"]*h-full[^"]*min-h-full[^"]*"/)
  assert.match(transition, /axis\(\{ paths: APP_ROUTES, type: 'x', variant: 'snappy' \}\)/)
  assert.match(transition, /prefersReducedMotion \? STATIC_CONFIG : MOTION_CONFIG/)
})

test('route-level loading, pixel indicators, and recovery boundaries remain available', async () => {
  const [loading, error, dataStates, matrix, authGate, workflowSession] = await Promise.all([
    read('app/(app)/loading.tsx'),
    read('app/(app)/error.tsx'),
    read('components/shell/data-states.tsx'),
    read('components/unlumen-ui/matrix.tsx'),
    read('components/auth/auth-gate.tsx'),
    read('components/flow/workflow-editor-session.tsx'),
  ])

  assert.match(loading, /<LoadingState rows=\{5\}/)
  assert.match(error, /<Button onClick=\{reset\}>重试当前视图<\/Button>/)
  assert.match(matrix, /export const loader:/)
  assert.match(dataStates, /frames=\{loader\}/)
  assert.match(dataStates, /size=\{5\}/)
  assert.match(authGate, /frames=\{loader\}/)
  assert.match(workflowSession, /ariaLabel="正在加载工作流"/)
})
