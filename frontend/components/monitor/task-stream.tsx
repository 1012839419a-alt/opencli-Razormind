'use client'

import Link from 'next/link'
import { AlertTriangle, ArrowRight, CheckCircle2 } from 'lucide-react'

import type { FailureItem, StreamTask } from '@/lib/demo/monitor'
import { formatDuration, formatRelative } from '@/lib/format'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const PHASE_STATUS: Record<StreamTask['phase'], string> = {
  queued: 'queued',
  running: 'running',
  success: 'success',
  failed: 'failed',
}

type GroupedStreamTask = StreamTask & { occurrences: number }
type GroupedFailure = FailureItem & { occurrences: number }

function groupStreamTasks(tasks: StreamTask[]): GroupedStreamTask[] {
  const grouped = new Map<string, GroupedStreamTask>()

  for (const task of tasks) {
    const key = [task.title, task.lane, task.workerName, task.phase].join('\u0000')
    const existing = grouped.get(key)
    if (existing) {
      existing.occurrences += 1
      existing.records += task.records
      continue
    }
    grouped.set(key, { ...task, occurrences: 1 })
  }

  return Array.from(grouped.values()).slice(0, 6)
}

function groupFailures(failures: FailureItem[]): GroupedFailure[] {
  const grouped = new Map<string, GroupedFailure>()

  for (const failure of failures) {
    const key = [failure.title, failure.workerName, failure.error].join('\u0000')
    const existing = grouped.get(key)
    if (existing) {
      existing.occurrences += 1
      continue
    }
    grouped.set(key, { ...failure, occurrences: 1 })
  }

  return Array.from(grouped.values()).slice(0, 5)
}

export function TaskStream({ tasks }: { tasks: StreamTask[] }) {
  const groupedTasks = groupStreamTasks(tasks)

  return (
    <Card size="sm" className="h-full">
      <CardHeader>
        <CardTitle className="text-base">最近运行</CardTitle>
        <CardDescription>每 30 秒刷新；相同任务、Worker 与状态已合并</CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>任务</TableHead>
              <TableHead>通道</TableHead>
              <TableHead>Worker</TableHead>
              <TableHead>状态</TableHead>
              <TableHead className="text-right">记录数</TableHead>
              <TableHead className="text-right">最近耗时</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {groupedTasks.map((t) => (
              <TableRow key={`${t.id}-${t.phase}`}>
                <TableCell className="max-w-52">
                  <span className="flex items-center gap-2">
                    {t.href ? (
                      <Link href={t.href} className="block min-w-0 truncate font-medium hover:underline">
                        {t.title}
                      </Link>
                    ) : (
                      <span className="block min-w-0 truncate font-medium">{t.title}</span>
                    )}
                    {t.occurrences > 1 ? (
                      <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                        ×{t.occurrences}
                      </Badge>
                    ) : null}
                  </span>
                  {t.retries > 0 ? (
                    <span className="text-xs text-warning">重试 ×{t.retries}</span>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-[10px]">
                    {t.lane === 'collect' ? '采集' : '发送'}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">{t.workerName}</TableCell>
                <TableCell>
                  <StatusBadge status={PHASE_STATUS[t.phase]} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {t.phase === 'queued' ? '—' : t.records}
                </TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {formatDuration(t.durationMs)}
                </TableCell>
              </TableRow>
            ))}
            {tasks.length === 0 ? (
              <TableRow data-stream-empty>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  当前没有排队或运行中的任务
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function FailureFeed({ failures }: { failures: FailureItem[] }) {
  const groupedFailures = groupFailures(failures)

  if (groupedFailures.length === 0) {
    return (
      <Card size="sm" aria-label="失败与重试">
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-md bg-success/10 text-success">
              <CheckCircle2 className="size-4" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium">当前没有失败任务</p>
              <p className="mt-0.5 text-xs text-muted-foreground">最近运行未发现需要重试或人工处理的异常。</p>
            </div>
          </div>
          <Link
            href="/tasks"
            className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            查看运行历史
            <ArrowRight className="size-3" aria-hidden />
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card size="sm" aria-label="失败与重试">
      <CardHeader className="border-b border-border/70">
        <CardTitle className="flex items-center gap-2 text-base">
          <AlertTriangle className="size-4 text-destructive" aria-hidden />
          失败与重试
        </CardTitle>
        <CardDescription>相同失败已合并，优先查看最新一次</CardDescription>
        <CardAction className="flex items-center gap-2">
          <Badge variant="destructive">{groupedFailures.length} 类异常</Badge>
          <Link
            href="/tasks?status=failed"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            查看全部
            <ArrowRight className="size-3" aria-hidden />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-border">
          {groupedFailures.map((f) => (
            <article
              key={f.id}
              className="grid gap-2 py-3 first:pt-0 last:pb-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {f.href ? (
                    <Link href={f.href} className="min-w-0 truncate text-sm font-medium hover:underline">
                      {f.title}
                    </Link>
                  ) : (
                    <span className="truncate text-sm font-medium">{f.title}</span>
                  )}
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatRelative(new Date(f.at).toISOString())}
                  </span>
                 </div>
                 <p className="mt-1 line-clamp-2 text-xs text-destructive">{f.error}</p>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground md:justify-end">
                <span className="font-mono">{f.workerName}</span>
                <span>{f.lane === 'collect' ? '采集' : '发送'}</span>
                {f.occurrences > 1 ? <span>同类失败 ×{f.occurrences}</span> : null}
                <span>{f.retries > 0 ? `已重试 ${f.retries} 次` : '未重试'}</span>
              </div>
            </article>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
