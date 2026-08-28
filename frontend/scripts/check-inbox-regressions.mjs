import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('inbox combines existing operational signals with server-backed human approvals', async () => {
  const page = await read('app/(app)/inbox/page.tsx')
  const approvalDetail = await read('components/inbox/queue-detail.tsx')
  const hooks = await read('lib/api/hooks.ts')
  const endpoints = await read('lib/api/endpoints.ts')

  assert.match(page, /useInfiniteTasks\(\{ status: 'failed', limit: 100 \}, \{ enabled: pendingActive \}\)/)
  assert.match(page, /useInfiniteTasks\(\{ status: 'pending', limit: 100 \}, \{ enabled: pendingActive \}\)/)
  assert.match(page, /useInfiniteNotificationLogs\(\{ limit: 100 \}, \{ enabled: pendingActive \}\)/)
  assert.match(page, /useInfiniteControlActions\(\s+\{ outcome: 'pending', limit: 100 \},\s+\{ enabled: pendingActive \},/)
  assert.match(hooks, /export function useInfiniteTasks/)
  assert.match(hooks, /export function useInfiniteNotificationLogs/)
  assert.match(hooks, /export function useInfiniteControlActions/)
  assert.match(endpoints, /listNotificationLogs = \(params\?: \{ rule_id\?: string; page\?: number; limit\?: number \}\)/)
  assert.match(page, /useGovernedWorkspaces\(\{ enabled: pendingActive \}\)/)
  assert.match(page, /useOperationsInbox\(workspaceId, 'open', \{ enabled: pendingActive \}\)/)
  assert.match(approvalDetail, /useDecideOperationsApproval\(\)/)
  assert.match(approvalDetail, /<AIApproval/)
  assert.match(approvalDetail, /审批理由（必填）/)
  assert.match(approvalDetail, /setCardRevision\(\(revision\) => revision \+ 1\)/)
  assert.match(hooks, /export function useOperationsInbox/)
  assert.match(hooks, /export function useDecideOperationsApproval/)
})

test('inbox uses a Linear-style queue while preserving canonical destinations for underlying records', async () => {
  const page = await read('app/(app)/inbox/page.tsx')
  const detail = await read('components/inbox/queue-detail.tsx')

  assert.match(page, /data-testid="inbox-workbench"/)
  assert.match(page, /lg:h-\[calc\(100dvh-3\.5rem\)\]/)
  assert.match(page, /data-testid="inbox-queue-scroll"/)
  assert.match(detail, /data-testid="inbox-detail-scroll"/)
  assert.doesNotMatch(page, /<PageContainer/)
  assert.doesNotMatch(page, /className="overflow-hidden rounded-xl border bg-card shadow-sm"/)
  assert.match(page, /ACTION_CENTER_TABS/)
  assert.match(page, /groupQueueItems/)
  assert.match(page, /role="listbox"/)
  assert.match(page, /aria-label="所选信号详情"/)
  assert.match(page, /搜索当前队列/)
  assert.match(page, /按严重程度排列，重复信号自动合并/)
  assert.match(page, /router\.push\(selectedItem\.href\)/)
  assert.match(page, /event\.key\.toLowerCase\(\) === 'j'/)
  assert.match(page, /event\.key\.toLowerCase\(\) === 'k'/)
  assert.match(page, /scrollIntoView\(\{ block: 'nearest' \}\)/)
  assert.match(page, /\[content-visibility:auto\]/)
  assert.match(page, /href: `\/tasks\/\$\{task\.id\}`/)
  assert.match(page, /href: '\/inbox\?tab=notifications'/)
  assert.match(page, /href: '\/inbox\?tab=controls'/)
  assert.match(detail, /href=\{`\/sources\/\$\{item\.sourceId\}`\}/)
})

test('inbox preserves queue state and progressively loads hundreds-scale signal sets', async () => {
  const page = await read('app/(app)/inbox/page.tsx')

  assert.match(page, /useSearchParams\(\)/)
  assert.match(page, /searchParams\.get\('view'\)/)
  assert.match(page, /searchParams\.get\('q'\)/)
  assert.match(page, /const searchParamsKey = searchParams\.toString\(\)/)
  assert.doesNotMatch(page, /\}, \[searchParams\]\)/)
  assert.match(page, /router\.replace\(/)
  assert.match(page, /\.pages\.flatMap\(\(page\) => page\.data\)/)
  assert.match(page, /hasMoreSignals/)
  assert.match(page, /isFetchingNextPage/)
  assert.match(page, /加载更多信号/)
  assert.match(page, /已加载/)
})

test('pending-only signals and shortcuts are disabled outside the pending pane', async () => {
  const page = await read('app/(app)/inbox/page.tsx')

  assert.match(page, /const pendingActive = activeTab === 'pending'/)
  assert.match(page, /if \(!pendingActive\) return/)
  assert.match(page, /\{pendingActive && partialFailures\.length > 0 \? \(/)
  assert.match(page, /\{pendingActive && approvalNotice \? \(/)
  assert.match(page, /\{pendingActive \? \(\s+<span/)
})

test('controls pane keeps the evidence ledger read-only and forwards its supported filters', async () => {
  const [inbox, ledger, hooks] = await Promise.all([
    read('app/(app)/inbox/page.tsx'),
    read('components/control/control-actions-ledger.tsx'),
    read('lib/api/hooks.ts'),
  ])

  assert.match(inbox, /<ControlActionsLedger \/>/)
  assert.match(ledger, /source_id: query\.get\('source_id'\) \?\? undefined/)
  assert.match(ledger, /mode: query\.get\('mode'\) \?\? undefined/)
  assert.match(ledger, /outcome: query\.get\('outcome'\) \?\? undefined/)
  assert.match(ledger, /useControlActions\(params\)/)
  assert.doesNotMatch(ledger, /use[A-Z]\w*(Mutation|Delete|Create|Update)/)
  assert.match(hooks, /export function useControlActions/)
})

test('inbox renders explicit initial, partial, empty, and total failure states', async () => {
  const page = await read('app/(app)/inbox/page.tsx')

  assert.match(page, /const isInitialLoading =\s+queries\.every/)
  assert.match(page, /const isTotalFailure =\s+queries\.every/)
  assert.match(page, /const partialFailures =/)
  assert.match(page, /暂时无法读取，其余信号仍可处理/)
  assert.match(page, /当前视图已经清空/)
  assert.match(page, /<LoadingState rows=\{5\}/)
  assert.match(page, /<ErrorState/)
  assert.match(page, /重新读取/)
})
