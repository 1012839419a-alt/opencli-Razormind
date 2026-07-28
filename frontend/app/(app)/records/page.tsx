'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Braces,
  ChevronLeft,
  ChevronRight,
  GitBranch,
  Rows3,
  Search,
  Sparkles,
  TableProperties,
} from 'lucide-react'

import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { DATA_EXPLORER_TABS, RouteTabs } from '@/components/shell/route-tabs'
import { StatusBadge } from '@/components/shell/status-badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useRecords } from '@/lib/api/hooks'
import type { CollectedRecord } from '@/lib/api/types'
import { formatRelative } from '@/lib/format'

const PAGE_SIZE = 50
const MAX_VISIBLE_FIELDS = 7
const PRIORITY_FIELDS = [
  'title',
  'name',
  'url',
  'text',
  'content',
  'description',
  'author',
  'published_at',
]

function recordPayload(record: CollectedRecord) {
  return Object.keys(record.normalized_data ?? {}).length > 0
    ? record.normalized_data
    : record.raw_data
}

function recordTitle(record: CollectedRecord): string {
  const data = recordPayload(record)
  const candidate = data.title ?? data.name ?? data.text ?? data.content ?? data.url
  if (typeof candidate === 'string' && candidate.trim()) return candidate
  return `记录 ${record.id.slice(0, 8)}`
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function shortId(value: string | null | undefined): string {
  if (!value) return '未绑定'
  return value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value
}

function JsonPanel({ label, value }: { label: string; value: Record<string, unknown> | undefined }) {
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <Braces className="size-3.5 text-muted-foreground" />
        <h3 className="text-sm font-medium">{label}</h3>
      </div>
      <pre className="max-h-72 overflow-auto rounded-lg border bg-muted/35 p-3 font-mono text-xs leading-5 text-foreground">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </section>
  )
}

function LineagePanel({ record }: { record: CollectedRecord }) {
  const lineage = [
    ['工作流', record.workflow_id],
    ['运行', record.workflow_run_id],
    ['来源节点', record.source_id],
    ['采集任务', record.task_id],
  ] as const

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <GitBranch className="size-3.5 text-muted-foreground" />
        <h3 className="text-sm font-medium">管线血缘</h3>
      </div>
      <div className="divide-y overflow-hidden rounded-lg border">
        {lineage.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[5rem_minmax(0,1fr)] gap-3 px-3 py-2.5 text-xs">
            <span className="text-muted-foreground">{label}</span>
            <code className="min-w-0 break-all font-mono text-foreground">{value ?? '未绑定'}</code>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function RecordsPage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selectedRecord, setSelectedRecord] = useState<CollectedRecord | null>(null)
  const recordsQuery = useRecords({
    ...(search ? { search } : {}),
    page,
    limit: PAGE_SIZE,
  })

  const records = useMemo(() => recordsQuery.data?.data ?? [], [recordsQuery.data?.data])
  const meta = recordsQuery.data?.meta
  const total = meta?.total ?? records.length
  const pages = Math.max(1, meta?.pages ?? 1)
  const visibleFields = useMemo(() => {
    const keys = new Set<string>()
    records.forEach((record) => {
      Object.keys(recordPayload(record)).forEach((key) => keys.add(key))
    })
    return [...keys]
      .filter((key) => !key.startsWith('_') && !key.startsWith('extra__workflow'))
      .sort((left, right) => {
        const leftPriority = PRIORITY_FIELDS.indexOf(left)
        const rightPriority = PRIORITY_FIELDS.indexOf(right)
        if (leftPriority >= 0 || rightPriority >= 0) {
          if (leftPriority < 0) return 1
          if (rightPriority < 0) return -1
          return leftPriority - rightPriority
        }
        return left.localeCompare(right)
      })
      .slice(0, MAX_VISIBLE_FIELDS)
  }, [records])
  const pipelineCount = useMemo(
    () => new Set(records.map((record) => record.workflow_id).filter(Boolean)).size,
    [records],
  )

  useEffect(() => {
    setPage(1)
    setSelectedRecord(null)
  }, [search])

  useEffect(() => {
    const linkedSearch = new URLSearchParams(window.location.search).get('search')
    if (linkedSearch) setSearch(linkedSearch)
  }, [])

  return (
    <PageContainer
      eyebrow="Data explorer"
      title="数据预览"
      description="直接查看采集结果的字段、内容和管线血缘；来源配置留在工作流节点中。"
      tabs={<RouteTabs tabs={DATA_EXPLORER_TABS} />}
      className="max-w-none"
    >
      <section className="overflow-hidden rounded-xl border bg-card">
        <header className="grid gap-4 border-b px-4 py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <TableProperties className="size-4 text-muted-foreground" />
              <h2 className="font-medium">记录内容</h2>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              当前页自动识别 {visibleFields.length} 个业务字段；点击记录 ID 查看标准化数据、原始数据和完整血缘。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <div>
              <div className="text-3xs text-muted-foreground">记录总量</div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums">{total.toLocaleString('zh-CN')}</div>
            </div>
            <div>
              <div className="text-3xs text-muted-foreground">当前字段</div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums">{visibleFields.length}</div>
            </div>
            <div>
              <div className="text-3xs text-muted-foreground">当前页管线</div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums">{pipelineCount}</div>
            </div>
          </div>
        </header>

        <div className="flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5" aria-label="当前数据字段">
            {visibleFields.length ? visibleFields.map((field) => (
              <code key={field} className="rounded-md bg-muted px-2 py-1 font-mono text-3xs text-muted-foreground">
                {field}
              </code>
            )) : <span className="text-xs text-muted-foreground">暂无可预览字段</span>}
          </div>
          <div className="relative w-full shrink-0 sm:w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索全部记录…"
              className="h-9 pl-8"
            />
          </div>
        </div>

        {recordsQuery.isLoading ? (
          <div className="p-4">
            <LoadingState rows={8} />
          </div>
        ) : recordsQuery.isError ? (
          <div className="p-4">
            <ErrorState message={(recordsQuery.error as Error)?.message} hint={BACKEND_HINT} />
          </div>
        ) : records.length === 0 ? (
          <div className="grid min-h-80 place-items-center p-8">
            <EmptyState title="暂无数据" description="运行采集管线后，记录字段和内容会显示在这里。" />
          </div>
        ) : (
          <>
            <div className="overflow-auto">
              <Table className="min-w-max">
                <TableHeader className="sticky top-0 z-10 bg-card shadow-[0_1px_0_hsl(var(--border))]">
                  <TableRow>
                    <TableHead className="w-32 bg-card">记录 ID</TableHead>
                    {visibleFields.map((field) => (
                      <TableHead key={field} className="min-w-44 max-w-72 bg-card font-mono text-xs">
                        {field}
                      </TableHead>
                    ))}
                    <TableHead className="w-36 bg-card">管线</TableHead>
                    <TableHead className="w-28 bg-card">状态</TableHead>
                    <TableHead className="w-24 bg-card">AI</TableHead>
                    <TableHead className="w-32 bg-card">采集时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {records.map((record) => {
                    const payload = recordPayload(record)
                    const enriched = Boolean(record.ai_enrichment && Object.keys(record.ai_enrichment).length > 0)
                    return (
                      <TableRow key={record.id} className="group">
                        <TableCell>
                          <button
                            type="button"
                            onClick={() => setSelectedRecord(record)}
                            className="inline-flex items-center gap-2 font-mono text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            aria-label={`查看${recordTitle(record)}详情`}
                          >
                            {record.id.slice(0, 8)}
                            <ChevronRight className="size-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                          </button>
                        </TableCell>
                        {visibleFields.map((field) => (
                          <TableCell key={field} className="max-w-72 truncate text-sm" title={formatCellValue(payload[field])}>
                            {formatCellValue(payload[field])}
                          </TableCell>
                        ))}
                        <TableCell>
                          <span className="font-mono text-xs text-muted-foreground" title={record.workflow_id ?? '未绑定工作流'}>
                            {shortId(record.workflow_id)}
                          </span>
                        </TableCell>
                        <TableCell><StatusBadge status={record.status} /></TableCell>
                        <TableCell>
                          {enriched ? (
                            <span className="inline-flex items-center gap-1 text-xs text-primary">
                              <Sparkles className="size-3.5" />
                              已富化
                            </span>
                          ) : <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatRelative(record.created_at)}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>

            <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
              <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                <Rows3 className="size-3.5" />
                第 {page.toLocaleString('zh-CN')} / {pages.toLocaleString('zh-CN')} 页，每页 {PAGE_SIZE} 行
              </span>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>
                  <ChevronLeft className="size-4" />
                  上一页
                </Button>
                <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage((current) => Math.min(pages, current + 1))}>
                  下一页
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>

      <Sheet open={Boolean(selectedRecord)} onOpenChange={(open) => !open && setSelectedRecord(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          {selectedRecord ? (
            <>
              <SheetHeader className="border-b pr-12">
                <SheetTitle>{recordTitle(selectedRecord)}</SheetTitle>
                <SheetDescription className="font-mono">
                  {selectedRecord.id} · {formatRelative(selectedRecord.created_at)}
                </SheetDescription>
              </SheetHeader>
              <div className="space-y-6 px-4 pb-6">
                <LineagePanel record={selectedRecord} />
                <JsonPanel label="标准化数据" value={selectedRecord.normalized_data} />
                <JsonPanel label="AI 富化" value={selectedRecord.ai_enrichment} />
                <JsonPanel label="原始数据" value={selectedRecord.raw_data} />
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </PageContainer>
  )
}
