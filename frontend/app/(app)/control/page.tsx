'use client'

import {
  useAdvisoryReport,
  useKillSwitch,
  useOdpState,
  useSetKillSwitch,
} from '@/lib/api/hooks'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatRelative } from '@/lib/format'
import type { AdvisoryReport, OdpSystemState } from '@/lib/api/types'

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' | 'muted' }) {
  const toneClass =
    tone === 'good' ? 'text-success' : tone === 'bad' ? 'text-destructive' : 'text-muted-foreground'
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`font-mono text-sm font-medium ${toneClass}`}>{value}</span>
    </div>
  )
}

function OdpSection({
  title,
  state,
  children,
}: {
  title: string
  state: { available: boolean; error?: string | null }
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{title}</span>
        {state.available ? (
          <StatusBadge status="healthy" />
        ) : (
          <StatusBadge status="offline" />
        )}
      </div>
      {state.available ? (
        <div className="grid grid-cols-2 gap-2">{children}</div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {state.error || '当前不可用（依赖的 Redis / 数据面未部署）'}
        </p>
      )}
    </div>
  )
}

function OdpPanels({ state }: { state: OdpSystemState }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <OdpSection title="Ingest 入口" state={state.ingest}>
        <Metric
          label="健康"
          value={state.ingest.healthy === true ? '健康' : state.ingest.healthy === false ? '异常' : '未知'}
          tone={state.ingest.healthy === true ? 'good' : state.ingest.healthy === false ? 'bad' : 'muted'}
        />
      </OdpSection>
      <OdpSection title="Stream 消费组" state={state.stream}>
        <Metric label="消费组" value={state.stream.group || '—'} />
        <Metric label="Lag" value={state.stream.lag == null ? '—' : String(state.stream.lag)} />
        <Metric label="Pending" value={state.stream.pending == null ? '—' : String(state.stream.pending)} />
        <Metric
          label="最旧滞留"
          value={state.stream.oldest_pending_idle_ms == null ? '—' : `${state.stream.oldest_pending_idle_ms}ms`}
        />
      </OdpSection>
      <OdpSection title="DLQ 死信" state={state.dlq}>
        <Metric label="总量" value={state.dlq.total == null ? '—' : String(state.dlq.total)} />
        <Metric label="近 24h" value={state.dlq.last_24h == null ? '—' : String(state.dlq.last_24h)} />
      </OdpSection>
      <OdpSection title="Store 存储" state={state.store}>
        <Metric label="心跳" value={state.store.heartbeat_age_seconds == null ? '—' : `${state.store.heartbeat_age_seconds}s`} />
      </OdpSection>
      <OdpSection title="Outbox" state={state.outbox}>
        <Metric label="未发布" value={state.outbox.unpublished == null ? '—' : String(state.outbox.unpublished)} />
      </OdpSection>
    </div>
  )
}

function AdvisoryTotalsRow({ report }: { report: AdvisoryReport }) {
  const t = report.totals
  return (
    <div className="flex flex-wrap gap-6">
      <Metric label="总数" value={String(t.total)} />
      <Metric label="待评估" value={String(t.pending)} />
      <Metric label="已评估" value={String(t.evaluated)} />
      <Metric label="已恢复" value={String(t.recovered)} tone="good" />
      <Metric label="已固化" value={String(t.persisted)} />
      <Metric
        label="恢复率"
        value={t.recovery_rate == null ? '—' : `${(t.recovery_rate * 100).toFixed(1)}%`}
        tone={t.recovery_rate != null && t.recovery_rate >= 0.8 ? 'bad' : 'muted'}
      />
    </div>
  )
}

export default function ControlCenterPage() {
  const kill = useKillSwitch()
  const setKill = useSetKillSwitch()
  const advisory = useAdvisoryReport()
  const odp = useOdpState()

  return (
    <PageContainer
      title="控制中心"
      eyebrow="CONTROL PLANE"
      description="执行熔断、自动模式门禁与共享数据面的系统级控制与观测。"
    >
      {/* ── Panel 1: Kill switch ─────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>执行熔断开关（Kill Switch）</CardTitle>
              <CardDescription>
                engaged 时无条件短路 Control Cycle 在 automatic 模式下的全部执行，下一次 tick 立即生效。
              </CardDescription>
            </div>
            <Switch
              checked={Boolean(kill.data?.engaged)}
              onCheckedChange={(v) => setKill.mutate(v)}
              disabled={setKill.isPending}
              aria-label="执行熔断开关"
            />
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-6">
          {kill.isLoading ? (
            <LoadingState rows={1} />
          ) : kill.isError ? (
            <ErrorState message={(kill.error as Error)?.message} hint={BACKEND_HINT} />
          ) : kill.data ? (
            <>
              <div className="flex items-center gap-2">
                {kill.data.engaged ? (
                  <Badge variant="destructive">已熔断</Badge>
                ) : (
                  <Badge variant="secondary">未熔断</Badge>
                )}
              </div>
              <Metric
                label="生效来源"
                value={
                  kill.data.runtime_override != null
                    ? '运行期覆盖'
                    : kill.data.config_default
                      ? '配置默认（启用）'
                      : '配置默认（停用）'
                }
              />
              <Metric
                label="运行期覆盖"
                value={kill.data.runtime_override == null ? '未设置' : kill.data.runtime_override ? '启用' : '停用'}
              />
              <Metric
                label="配置默认"
                value={kill.data.config_default ? '启用' : '停用'}
                tone={kill.data.config_default ? 'bad' : 'muted'}
              />
              {kill.data.engaged ? (
                <Badge variant="destructive">所有自动执行将在下一次 tick 被短路</Badge>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Panel 2: Advisory report ─────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>咨询报告（Advisory Report）</CardTitle>
          <CardDescription>
            control_actions 证据台账的收敛/恢复统计 —— 某个 (state, action_type) 组合的建议大多「已恢复」说明该处过度建议，
            不应自动化；大多「已固化」才具备翻转 automatic 模式的门禁资格。读取时自动完成一次懒评估。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {advisory.isLoading ? (
            <LoadingState rows={3} />
          ) : advisory.isError ? (
            <ErrorState message={(advisory.error as Error)?.message} hint={BACKEND_HINT} />
          ) : advisory.data ? (
            <>
              <AdvisoryTotalsRow report={advisory.data} />
              {advisory.data.buckets.length === 0 ? (
                <EmptyState title="暂无台账数据" description="控制器产生建议或执行动作后，分桶统计会显示在此。" />
              ) : (
                <Card className="overflow-hidden py-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>状态类别</TableHead>
                        <TableHead>动作类型</TableHead>
                        <TableHead className="text-right">总数</TableHead>
                        <TableHead className="text-right">待评估</TableHead>
                        <TableHead className="text-right">已恢复</TableHead>
                        <TableHead className="text-right">已固化</TableHead>
                        <TableHead className="text-right">恢复率</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {advisory.data.buckets.map((b) => (
                        <TableRow key={`${b.state}/${b.action_type}`}>
                          <TableCell>
                            <StatusBadge status={b.state} />
                          </TableCell>
                          <TableCell className="font-mono text-xs font-medium">{b.action_type}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{b.total}</TableCell>
                          <TableCell className="text-right font-mono text-xs text-muted-foreground">{b.pending}</TableCell>
                          <TableCell className="text-right font-mono text-xs text-success">{b.recovered}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{b.persisted}</TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {b.recovery_rate == null ? '—' : `${(b.recovery_rate * 100).toFixed(1)}%`}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              )}
              <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                <span>模式分布：</span>
                {Object.entries(advisory.data.mode_breakdown).map(([mode, count]) => (
                  <Badge key={mode} variant={mode === 'automatic' ? 'default' : 'outline'}>
                    {mode === 'automatic' ? '自动' : '建议'} × {count}
                  </Badge>
                ))}
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* ── Panel 3: ODP data-plane state ────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>ODP 数据面状态</CardTitle>
              <CardDescription>
                共享数据平面（Redis 消费组 / 死信队列 / 存储心跳）的系统级健康，与单数据源无关。
                任一环节不可用只降级自身区块，不影响其他区块。
              </CardDescription>
            </div>
            {odp.data ? (
              <span className="font-mono text-xs text-muted-foreground">
                {formatRelative(odp.data.collected_at)}
              </span>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          {odp.isLoading ? (
            <LoadingState rows={3} />
          ) : odp.isError ? (
            <ErrorState message={(odp.error as Error)?.message} hint={BACKEND_HINT} />
          ) : odp.data ? (
            <OdpPanels state={odp.data} />
          ) : null}
        </CardContent>
      </Card>
    </PageContainer>
  )
}
