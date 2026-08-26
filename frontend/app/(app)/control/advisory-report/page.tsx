'use client'

import { useAdvisoryReport } from '@/lib/api/hooks'
import type { AdvisoryReportBucket } from '@/lib/api/types'
import { formatNumber } from '@/lib/format'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

function formatRate(rate: number | null) {
  return rate === null ? '—' : `${(rate * 100).toFixed(1)}%`
}

function StatTile({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'success' | 'danger' | 'muted'
}) {
  const toneClass = tone === 'success' ? 'text-success' : tone === 'danger' ? 'text-destructive' : undefined
  return (
    <Card size="sm">
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`font-mono text-xl tabular-nums ${toneClass ?? ''}`}>{formatNumber(value)}</div>
      </CardContent>
    </Card>
  )
}

// Agreement/recovery report over the control_actions evidence ledger
// (PR-Control-3.5) — the gate data for ever flipping CONTROL_MODE to
// "automatic" per (state, action_type) bucket. Advisory-only: nothing here
// executes anything, it only reports what already happened.
export default function AdvisoryReportPage() {
  const { data, isLoading, isError, error } = useAdvisoryReport()

  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
  if (!data) return <ErrorState message="未收到建议报告数据" hint={BACKEND_HINT} />

  const { totals, buckets, mode_breakdown, evaluation } = data

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-sm font-medium text-muted-foreground">证据台账总览</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <StatTile label="总计" value={totals.total} />
          <StatTile label="待评估" value={totals.pending} />
          <StatTile label="已评估" value={totals.evaluated} />
          <StatTile label="已恢复" value={totals.recovered} tone="success" />
          <StatTile label="未恢复" value={totals.persisted} tone="danger" />
          <StatTile label="数据不足" value={totals.insufficient_data} tone="muted" />
          <Card size="sm">
            <CardHeader className="pb-1">
              <CardTitle className="text-xs font-medium text-muted-foreground">恢复率</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="font-mono text-xl tabular-nums">{formatRate(totals.recovery_rate)}</div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">本次读取触发的评估</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-x-6 gap-y-2 border-t pt-3 text-sm text-muted-foreground">
          <span>
            已评估 <span className="font-medium text-foreground">{formatNumber(evaluation.evaluated)}</span>
          </span>
          <span>
            恢复 <span className="font-medium text-foreground">{formatNumber(evaluation.recovered)}</span>
          </span>
          <span>
            未恢复 <span className="font-medium text-foreground">{formatNumber(evaluation.persisted)}</span>
          </span>
          <span>
            数据不足 <span className="font-medium text-foreground">{formatNumber(evaluation.insufficient_data)}</span>
          </span>
          <span>
            仍待评估 <span className="font-medium text-foreground">{formatNumber(evaluation.still_pending)}</span>
          </span>
        </CardContent>
      </Card>

      {Object.keys(mode_breakdown).length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">决策模式分布</span>
          {Object.entries(mode_breakdown).map(([mode, count]) => (
            <Badge key={mode} variant={mode === 'automatic' ? 'default' : 'outline'}>
              {mode === 'automatic' ? '自动' : mode === 'advisory' ? '建议' : mode}：{formatNumber(count)}
            </Badge>
          ))}
        </div>
      ) : null}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">自动化门禁分桶（按状态 × 动作类型）</h2>
        {buckets.length === 0 ? (
          <EmptyState
            title="暂无建议数据"
            description="控制器产生并评估建议后，按（状态、动作类型）分组的数据会显示在此。"
          />
        ) : (
          <Card className="overflow-hidden py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>状态</TableHead>
                  <TableHead>动作类型</TableHead>
                  <TableHead className="text-right">总计</TableHead>
                  <TableHead className="text-right">待评估</TableHead>
                  <TableHead className="text-right">已恢复</TableHead>
                  <TableHead className="text-right">未恢复</TableHead>
                  <TableHead className="text-right">数据不足</TableHead>
                  <TableHead className="text-right">恢复率</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {buckets.map((bucket: AdvisoryReportBucket) => (
                  <TableRow key={`${bucket.state}:${bucket.action_type}`}>
                    <TableCell>
                      <StatusBadge status={bucket.state} />
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium">{bucket.action_type}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(bucket.total)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumber(bucket.pending)}</TableCell>
                    <TableCell className="text-right tabular-nums text-success">
                      {formatNumber(bucket.recovered)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-destructive">
                      {formatNumber(bucket.persisted)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {formatNumber(bucket.insufficient_data)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatRate(bucket.recovery_rate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>
    </div>
  )
}
