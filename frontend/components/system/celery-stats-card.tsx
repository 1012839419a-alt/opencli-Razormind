'use client'

import { Cpu } from 'lucide-react'

import { useCeleryStats, useSystemConfig } from '@/lib/api/hooks'
import { formatNumber } from '@/lib/format'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

// GET /workers/celery-stats returns raw `celery.control.inspect()` output
// (backend/api/v1/workers.py celery_stats), which is why the endpoint wrapper
// types it as Record<string, unknown> rather than a real contract — the shape
// is Celery's, not ours, and varies by broker/version. Everything below reads
// it defensively instead of trusting a schema.
type CeleryWorkerRaw = {
  hostname?: string
  pid?: number
  pool?: { 'max-concurrency'?: number }
  total?: Record<string, number>
}

type CeleryStatsPayload = {
  // Present when the backend's own inspect() call raised (e.g. no broker
  // reachable) — it still returns 200 with this shape instead of a 5xx.
  error?: string
  stats?: Record<string, CeleryWorkerRaw>
  active?: Record<string, unknown[]>
}

function sumTaskCounts(total?: Record<string, number>): number {
  if (!total) return 0
  return Object.values(total).reduce((sum, n) => sum + (typeof n === 'number' ? n : 0), 0)
}

export function CeleryStatsCard() {
  const { data, isLoading, isError, error } = useCeleryStats()
  const { data: config } = useSystemConfig()
  const payload = (data ?? {}) as CeleryStatsPayload
  const stats = payload.stats ?? {}
  const active = payload.active ?? {}
  const workerIds = Object.keys(stats)

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Cpu className="size-4" /> Celery Worker 状态
        </CardTitle>
        <CardDescription>
          {workerIds.length > 0 ? `${workerIds.length} 个 Worker 在线` : '分布式任务执行器的实时状态'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        {isLoading ? (
          <LoadingState rows={2} />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : payload.error ? (
          <EmptyState
            title={config?.task_executor === 'local' ? '当前使用本地执行器' : '无法连接 Celery'}
            description={
              config?.task_executor === 'local'
                ? '系统配置中任务执行器为 local（进程内 asyncio），未使用 Celery，因此没有 Worker 统计。'
                : payload.error
            }
          />
        ) : workerIds.length === 0 ? (
          <EmptyState title="暂无 Celery Worker" description="还没有 Worker 连接到消息队列。" />
        ) : (
          <div className="flex flex-col gap-2">
            {workerIds.map((id) => {
              const info = stats[id]
              const activeCount = active[id]?.length ?? 0
              const concurrency = info.pool?.['max-concurrency']
              const totalProcessed = sumTaskCounts(info.total)
              return (
                <div
                  key={id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/15 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate font-mono text-xs font-medium">{info.hostname ?? id}</p>
                    <p className="text-xs text-muted-foreground">
                      {info.pid != null ? `PID ${info.pid}` : '—'}
                      {concurrency != null ? ` · 并发 ${concurrency}` : ''}
                      {' · 累计处理 '}
                      {formatNumber(totalProcessed)}
                    </p>
                  </div>
                  <Badge variant={activeCount > 0 ? 'default' : 'outline'}>
                    {activeCount > 0 ? `${activeCount} 个活跃任务` : '空闲'}
                  </Badge>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
