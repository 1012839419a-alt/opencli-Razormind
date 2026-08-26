'use client'

import { ArrowUpRight, ChevronLeft, ChevronRight } from 'lucide-react'
import Link from 'next/link'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

import { useTasks } from '@/lib/api/hooks'
import { formatRelative } from '@/lib/format'
import {
  normalizeTaskPage,
  normalizeTaskStatus,
  pathWithQuery,
  queryForTaskPage,
  queryForTaskStatus,
} from '@/lib/tasks/query'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ACTION_CENTER_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { StatusBadge } from '@/components/shell/status-badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const STATUS_FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
  { key: 'pending', label: '等待中' },
]
const TASKS_PER_PAGE = 50

export default function TasksPage() {
  return (
    <Suspense fallback={<TasksPageLoading />}>
      <TasksPageContent />
    </Suspense>
  )
}

function TasksPageLoading() {
  return (
    <PageContainer
      eyebrow="Task history"
      title="任务与通知"
      description="查看所有采集工作项及其执行状态；需要立即处理的异常会进入待处理视图。"
      tabs={<RouteTabs tabs={ACTION_CENTER_TABS} />}
    >
      <LoadingState />
    </PageContainer>
  )
}

function TasksPageContent() {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const status = normalizeTaskStatus(searchParams.get('status'))
  const page = normalizeTaskPage(searchParams.get('page'))
  const { data, isLoading, isError, error } = useTasks({
    ...(status ? { status } : {}),
    page,
    limit: TASKS_PER_PAGE,
  })
  const tasks = data?.data ?? []
  const activeFilter = STATUS_FILTERS.find((filter) => filter.key === status) ?? STATUS_FILTERS[0]
  const currentPage = data?.meta?.page ?? page
  const totalPages = Math.max(data?.meta?.pages ?? 1, 1)
  const totalTasks = data?.meta?.total ?? tasks.length

  function selectStatus(nextStatus: string) {
    const query = queryForTaskStatus(searchParams.toString(), nextStatus)
    router.replace(pathWithQuery(pathname, query), { scroll: false })
  }

  function selectPage(nextPage: number) {
    const query = queryForTaskPage(searchParams.toString(), nextPage)
    router.replace(pathWithQuery(pathname, query), { scroll: false })
  }

  return (
    <PageContainer
      eyebrow="Task history"
      title="任务与通知"
      description="查看所有采集工作项及其执行状态；需要立即处理的异常会进入待处理视图。"
      tabs={<RouteTabs tabs={ACTION_CENTER_TABS} />}
      actions={
        <div className="flex items-center gap-1 rounded-md border p-0.5">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.key}
              size="sm"
              variant={status === f.key ? 'secondary' : 'ghost'}
              className="h-7"
              aria-pressed={status === f.key}
              onClick={() => selectStatus(f.key)}
            >
              {f.label}
            </Button>
          ))}
        </div>
      }
    >
      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : tasks.length === 0 ? (
        <div className="space-y-3">
          <EmptyState
            title={page > 1 ? '这一页没有任务' : status ? `暂无${activeFilter.label}任务` : '暂无任务'}
            description={page > 1 ? '任务数量可能已经变化，请返回第一页继续查看。' : status ? '当前筛选条件下没有任务，可切换状态查看其他工作项。' : '触发采集后，任务会显示在此。'}
          />
          {page > 1 ? <Button variant="outline" onClick={() => selectPage(1)}>返回第一页</Button> : null}
        </div>
      ) : (
        <div className="space-y-3">
          <Card className="overflow-hidden py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>数据源</TableHead>
                  <TableHead>触发方式</TableHead>
                  <TableHead>优先级</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((t) => (
                  <TableRow key={t.id} className="group">
                    <TableCell className="font-medium">
                      <Link href={`/tasks/${t.id}`} className="flex items-center gap-2 hover:underline">
                        <span>{t.source_name ?? t.source_id}</span>
                        <ArrowUpRight className="size-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{t.trigger_type}</TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">{t.priority}</TableCell>
                    <TableCell>
                      <StatusBadge status={t.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatRelative(t.created_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <nav className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground" aria-label="任务分页">
            <span>共 {totalTasks} 个任务 · 第 {currentPage} / {totalPages} 页</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => selectPage(currentPage - 1)}>
                <ChevronLeft className="size-4" />上一页
              </Button>
              <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => selectPage(currentPage + 1)}>
                下一页<ChevronRight className="size-4" />
              </Button>
            </div>
          </nav>
        </div>
      )}
    </PageContainer>
  )
}
