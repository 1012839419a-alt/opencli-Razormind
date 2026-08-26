'use client'

import type { ReactNode } from 'react'
import { AlertCircle, Database, Layers, MessageSquareWarning, Radio, Server } from 'lucide-react'

import { useOdpState } from '@/lib/api/hooks'
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

// available=false / healthy=null are legitimate "sensor couldn't be reached"
// states, never coerced into a fabricated "healthy" reading — see
// backend/schemas/odp_state.py. Map that directly onto the shared status
// vocabulary rather than inventing a fourth tone.
function healthStatus(available: boolean, healthy: boolean | null) {
  if (!available || healthy === null) return 'unknown'
  return healthy ? 'healthy' : 'degraded'
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value}</span>
    </div>
  )
}

function SectionCard({
  icon: Icon,
  title,
  status,
  error,
  note,
  children,
}: {
  icon: typeof Database
  title: string
  status: string
  error?: string | null
  note?: string
  children?: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className="size-4 text-muted-foreground" aria-hidden />
          {title}
        </CardTitle>
        <StatusBadge status={status} />
      </CardHeader>
      <CardContent className="space-y-2 border-t pt-3">
        {children}
        {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
        {error ? (
          <p className="flex items-start gap-1.5 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            {error}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

// System-level (not per-source) ODP data-plane snapshot (C2). Every section
// carries its own `available` flag — store/outbox are unavailable BY DESIGN
// (no heartbeat table, no outbox table), not a degraded reading, so they
// render as "unknown" with an explanatory note rather than a red error.
export default function OdpStatePage() {
  const { data, isLoading, isError, error } = useOdpState()

  if (isLoading) return <LoadingState />
  if (isError) return <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
  if (!data) return <ErrorState message="未收到 ODP 状态数据" hint={BACKEND_HINT} />

  const { ingest, stream, dlq, store, outbox, collected_at } = data

  return (
    <div className="flex flex-col gap-6">
      <p className="text-xs text-muted-foreground">
        采集时间 {formatDateTime(collected_at)}（{formatRelative(collected_at)}）· 每 15 秒自动刷新
      </p>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <SectionCard
          icon={Radio}
          title="odp-ingest 健康"
          status={healthStatus(ingest.available, ingest.healthy)}
          error={ingest.error}
        >
          <Row label="可用" value={ingest.available ? '是' : '否'} />
          <Row
            label="健康"
            value={!ingest.available ? '—' : ingest.healthy === null ? '未知' : ingest.healthy ? '是' : '否'}
          />
        </SectionCard>

        <SectionCard
          icon={Layers}
          title="Redis 消费组"
          status={stream.available ? 'healthy' : 'unknown'}
          error={stream.error}
        >
          <Row label="Stream" value={stream.name} />
          <Row label="Group" value={stream.group} />
          <Row label="未投递积压 (lag)" value={stream.lag === null ? '—' : formatNumber(stream.lag)} />
          <Row label="已投递未确认 (pending)" value={stream.pending === null ? '—' : formatNumber(stream.pending)} />
          <Row
            label="最旧待确认空闲时长"
            value={stream.oldest_pending_idle_ms === null ? '—' : `${formatNumber(stream.oldest_pending_idle_ms)} ms`}
          />
        </SectionCard>

        <SectionCard
          icon={MessageSquareWarning}
          title="死信队列 (DLQ)"
          status={!dlq.available ? 'unknown' : dlq.total ? 'degraded' : 'healthy'}
          error={dlq.error}
        >
          <Row label="累计" value={dlq.total === null ? '—' : formatNumber(dlq.total)} />
          <Row label="近 24 小时" value={dlq.last_24h === null ? '—' : formatNumber(dlq.last_24h)} />
        </SectionCard>

        <SectionCard icon={Database} title="odp-store 存活" status="unknown" note={store.note}>
          <Row label="可用" value="否" />
          <Row
            label="心跳年龄"
            value={store.heartbeat_age_seconds === null ? '—' : `${formatNumber(store.heartbeat_age_seconds)} s`}
          />
        </SectionCard>

        <SectionCard icon={Server} title="未发布 Outbox 积压" status="unknown" note={outbox.note}>
          <Row label="可用" value="否" />
          <Row label="未发布数量" value={outbox.unpublished === null ? '—' : formatNumber(outbox.unpublished)} />
        </SectionCard>
      </div>
    </div>
  )
}
