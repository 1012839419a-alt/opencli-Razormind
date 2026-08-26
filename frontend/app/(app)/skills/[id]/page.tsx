'use client'

import { use, useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Clock3,
  FileWarning,
  History,
  RotateCcw,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'

import { useDismissCorrection, useRollbackSkill, useSkill } from '@/lib/api/hooks'
import type { SkillEvidenceEntry } from '@/lib/api/types'
import { formatDateTime, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { BACKEND_HINT, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const LIFECYCLE_LABEL: Record<string, string> = {
  draft: '草稿',
  active: '生效中',
  deprecated: '已弃用',
}

const EVENT_META: Record<string, { label: string; tone: string; icon: typeof Clock3 }> = {
  executed: { label: '执行', tone: 'text-muted-foreground', icon: Clock3 },
  corrected: { label: '重蒸馏', tone: 'text-primary', icon: Sparkles },
  correction_dismissed: { label: '已忽略提案', tone: 'text-muted-foreground', icon: Ban },
  correction_proposed: { label: '提出纠正建议', tone: 'text-warning', icon: AlertTriangle },
  rolled_back: { label: '已回滚', tone: 'text-destructive', icon: RotateCcw },
}

function eventMeta(event: string) {
  return EVENT_META[event] ?? { label: event, tone: 'text-muted-foreground', icon: Clock3 }
}

function strOr(value: unknown, fallback = '—'): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback
}

/** Mirrors the backend's `_has_open_proposal` / `_correction_boundary` rule
 * (backend/api/v1/skills.py, backend/skills/correction.py): the index just
 * past the most recent `corrected` / `correction_dismissed` entry resets the
 * streak, then an open proposal is a `correction_proposed` at or after that
 * boundary. Returns the entry itself (not just a boolean) so the UI can show
 * why it was proposed. */
function openProposal(evidence: SkillEvidenceEntry[]): SkillEvidenceEntry | null {
  let boundary = 0
  evidence.forEach((ev, i) => {
    if (ev.event === 'corrected' || ev.event === 'correction_dismissed') boundary = i + 1
  })
  for (let i = evidence.length - 1; i >= boundary; i--) {
    if (evidence[i].event === 'correction_proposed') return evidence[i]
  }
  return null
}

/** Mirrors the backend's `rollback_correction` guard (backend/skills/correction.py):
 * the most recent `corrected` entry, unless a `rolled_back` referencing its
 * `to_version` already appears after it. Client-side only, for the button's
 * enabled/disabled hint — the backend stays authoritative and still 400s on a
 * stale read (e.g. two tabs open). */
function findRollbackTarget(evidence: SkillEvidenceEntry[]): SkillEvidenceEntry | null {
  for (let i = evidence.length - 1; i >= 0; i--) {
    if (evidence[i].event === 'corrected') {
      const toVersion = evidence[i].to_version
      const alreadyRolledBack = evidence
        .slice(i + 1)
        .some((ev) => ev.event === 'rolled_back' && ev.from_version === toVersion)
      return alreadyRolledBack ? null : evidence[i]
    }
  }
  return null
}

function renderEventBadge(ev: SkillEvidenceEntry) {
  if (ev.event === 'executed') {
    return <Badge variant={ev.passed ? 'secondary' : 'destructive'}>{ev.passed ? '通过' : '未通过'}</Badge>
  }
  if (ev.event === 'corrected' || ev.event === 'rolled_back') {
    return (
      <Badge variant="outline">
        v{String(ev.from_version ?? '?')} → v{String(ev.to_version ?? '?')}
      </Badge>
    )
  }
  return null
}

function renderEventDetail(ev: SkillEvidenceEntry) {
  if (ev.event === 'executed') {
    const milestones = Array.isArray(ev.milestones_hit) ? ev.milestones_hit.length : 0
    return (
      <p className="mt-1 text-sm text-muted-foreground">
        结果 {strOr(ev.outcome)} · loop {strOr(ev.loop_outcome)}
        {milestones ? ` · 命中里程碑 ${milestones} 个` : ''}
      </p>
    )
  }
  if (ev.event === 'correction_proposed') {
    const traceCount = Array.isArray(ev.trace_ids) ? ev.trace_ids.length : 0
    return (
      <p className="mt-1 text-sm text-muted-foreground">
        {traceCount ? `连续 ${traceCount} 次失败` : '连续失败'} · 此前已重蒸馏 {String(ev.prior_redistill_count ?? 0)} 次
      </p>
    )
  }
  if (ev.event === 'corrected') {
    return (
      <p className="mt-1 text-sm text-muted-foreground">
        源 trace <span className="font-mono text-xs">{strOr(ev.trace_id)}</span>
      </p>
    )
  }
  return null
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-lg font-semibold tabular-nums">{value}</span>
    </div>
  )
}

function ContextRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b pb-3 last:border-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('max-w-56 text-right break-all', mono && 'font-mono text-xs')}>{value}</span>
    </div>
  )
}

export default function SkillDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { data: skill, isLoading, isError, error } = useSkill(id)
  const dismissCorrection = useDismissCorrection()
  const rollbackSkill = useRollbackSkill()

  const [confirmDismiss, setConfirmDismiss] = useState(false)
  const [confirmRollback, setConfirmRollback] = useState(false)

  const evidence = skill?.evidence ?? []
  const proposal = openProposal(evidence)
  const rollbackTarget = findRollbackTarget(evidence)

  const trace = skill?.last_failing_trace ?? null
  const traceSummary = (trace?.summary as Record<string, unknown> | undefined) ?? {}
  const traceOutcome = (trace?.outcome as Record<string, unknown> | undefined) ?? {}
  const traceStepsCount = Array.isArray(trace?.steps) ? (trace!.steps as unknown[]).length : 0

  async function handleDismiss() {
    if (!skill) return
    try {
      await dismissCorrection.mutateAsync(skill.id)
      toast.success('已忽略该纠正建议')
      setConfirmDismiss(false)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : '操作失败')
    }
  }

  async function handleRollback() {
    if (!skill) return
    try {
      await rollbackSkill.mutateAsync(skill.id)
      toast.success('已回滚到上一版本')
      setConfirmRollback(false)
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : '回滚失败')
    }
  }

  return (
    <PageContainer
      eyebrow="Automation"
      title={skill?.name ?? `技能 ${id.slice(0, 8)}`}
      description={
        skill
          ? `${skill.domain} / ${skill.capability} · v${skill.version}`
          : '查看技能详情、纠正提案与版本历史。'
      }
      actions={
        <Link href="/skills" className={cn(buttonVariants({ variant: 'outline', size: 'sm' }))}>
          <ArrowLeft className="size-4" />
          返回列表
        </Link>
      }
    >
      {isLoading ? (
        <LoadingState rows={4} />
      ) : isError ? (
        <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
      ) : skill ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-4">
                <div>
                  <CardTitle className="text-base">技能概览</CardTitle>
                  <CardDescription>录制 → 蒸馏 → 执行 → 纠正闭环的当前状态。</CardDescription>
                </div>
                <StatusBadge status={skill.enabled ? 'enabled' : 'disabled'} />
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="领域 / 能力" value={`${skill.domain} / ${skill.capability}`} />
                <Metric label="版本" value={`v${skill.version}`} />
                <Metric label="生命周期" value={LIFECYCLE_LABEL[skill.status] ?? skill.status} />
                <Metric label="证据条数" value={formatNumber(skill.evidence_count)} />
              </CardContent>
              {skill.scope ? (
                <CardContent className="pt-0 text-sm">
                  <span className="text-muted-foreground">适用范围 </span>
                  {skill.scope}
                </CardContent>
              ) : null}
            </Card>

            {proposal ? (
              <Card className="ring-1 ring-warning/30">
                <CardHeader className="flex flex-row items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="size-4 text-warning" />
                    <CardTitle className="text-base">待复核的纠正建议</CardTitle>
                  </div>
                  <Badge variant="secondary" className="bg-warning/10 text-warning">
                    待复核
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-muted-foreground">
                    {Array.isArray(proposal.trace_ids) && proposal.trace_ids.length > 0
                      ? `连续 ${proposal.trace_ids.length} 次执行未通过自检，`
                      : '连续执行未通过自检，'}
                    系统提出了重蒸馏建议
                    {typeof proposal.prior_redistill_count === 'number'
                      ? `（此前已重蒸馏 ${proposal.prior_redistill_count} 次）`
                      : ''}
                    。提出时间 {formatDateTime(proposal.at)}。
                  </p>
                  {Array.isArray(proposal.trace_ids) && proposal.trace_ids.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {proposal.trace_ids.map((tid, i) => (
                        <Badge key={i} variant="outline" className="font-mono text-[10px]">
                          {String(tid)}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            {trace ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <FileWarning className="size-4 text-muted-foreground" />
                    触发纠正的失败轨迹
                  </CardTitle>
                  <CardDescription>
                    最近一次失败执行的 journey_trace_v1 —— 重蒸馏未显式传入 trace 时的兜底来源。
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Metric label="Trace ID" value={strOr(trace.trace_id)} />
                    <Metric label="标签" value={strOr(trace.label)} />
                    <Metric label="结果" value={strOr(traceOutcome.status)} />
                    <Metric label="步骤数" value={formatNumber(traceStepsCount)} />
                  </div>
                  <details className="rounded-lg border">
                    <summary className="cursor-pointer select-none px-4 py-2 text-sm text-muted-foreground hover:text-foreground">
                      查看完整 trace JSON
                    </summary>
                    <pre className="max-h-72 overflow-auto rounded-b-lg border-t bg-muted/25 p-4 font-mono text-xs leading-5">
                      {JSON.stringify(trace, null, 2)}
                    </pre>
                  </details>
                  {strOr(traceSummary.domain, '') ? (
                    <p className="text-xs text-muted-foreground">摘要领域: {strOr(traceSummary.domain)}</p>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}

            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                  <History className="size-4 text-muted-foreground" />
                  <CardTitle className="text-base">证据时间线</CardTitle>
                </div>
                <Badge variant="outline">{formatNumber(evidence.length)} 条</Badge>
              </CardHeader>
              <CardContent>
                {evidence.length === 0 ? (
                  <p className="text-sm text-muted-foreground">该技能尚未产生任何执行或纠正记录。</p>
                ) : (
                  <ol className="relative ml-2 max-h-[36rem] space-y-5 overflow-y-auto border-l pl-5">
                    {[...evidence].reverse().map((ev, idx) => {
                      const meta = eventMeta(ev.event)
                      const Icon = meta.icon
                      return (
                        <li key={evidence.length - 1 - idx} className="relative">
                          <span
                            className={cn(
                              'absolute -left-[1.65rem] top-0.5 flex size-5 items-center justify-center rounded-full border-2 border-background bg-background',
                              meta.tone,
                            )}
                          >
                            <Icon className="size-3" />
                          </span>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={cn('text-sm font-medium', meta.tone)}>{meta.label}</span>
                            {renderEventBadge(ev)}
                            <span className="text-xs text-muted-foreground">{formatDateTime(ev.at)}</span>
                          </div>
                          {renderEventDetail(ev)}
                        </li>
                      )
                    })}
                  </ol>
                )}
              </CardContent>
            </Card>
          </div>

          <aside className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">纠正操作</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <div className="space-y-1.5">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    disabled={!proposal}
                    onClick={() => setConfirmDismiss(true)}
                  >
                    <Ban className="size-4" />
                    忽略纠正建议
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    {proposal ? '清除待复核标记，不修改技能内容，重新计数下一轮连续失败。' : '当前没有待复核的提案。'}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    disabled={!rollbackTarget}
                    onClick={() => setConfirmRollback(true)}
                  >
                    <RotateCcw className="size-4" />
                    回滚到上一版本
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    {rollbackTarget
                      ? `撤销最近一次重蒸馏，将内容恢复为 v${String(rollbackTarget.from_version)}。`
                      : '没有可撤销的重蒸馏记录。'}
                  </p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">当前技能内容</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <ContextRow label="蒸馏模型" value={strOr(skill.distill_model)} mono />
                <ContextRow label="来源 Trace" value={strOr(skill.source_trace)} mono />
                {skill.skill_md ? (
                  <details className="rounded-lg border">
                    <summary className="cursor-pointer select-none px-3 py-2 text-xs text-muted-foreground hover:text-foreground">
                      查看 SKILL.md
                    </summary>
                    <pre className="max-h-72 overflow-auto rounded-b-lg border-t bg-muted/25 p-3 font-mono text-xs leading-5 whitespace-pre-wrap">
                      {skill.skill_md}
                    </pre>
                  </details>
                ) : (
                  <p className="text-muted-foreground">尚未生成 SKILL.md。</p>
                )}
              </CardContent>
            </Card>
          </aside>
        </div>
      ) : null}

      <Dialog
        open={confirmDismiss}
        onOpenChange={(open) => !open && !dismissCorrection.isPending && setConfirmDismiss(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>忽略这条纠正建议？</DialogTitle>
            <DialogDescription>
              系统认为该技能连续失败已达到阈值，标记为待复核。忽略后不会修改技能内容，只会清除该提醒，并重新开始计数下一轮连续失败。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDismiss(false)} disabled={dismissCorrection.isPending}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => void handleDismiss()} disabled={dismissCorrection.isPending}>
              {dismissCorrection.isPending ? '正在处理…' : '确认忽略'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={confirmRollback}
        onOpenChange={(open) => !open && !rollbackSkill.isPending && setConfirmRollback(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>回滚到上一版本？</DialogTitle>
            <DialogDescription>
              {rollbackTarget
                ? `将 v${String(rollbackTarget.to_version)} 的内容恢复为 v${String(rollbackTarget.from_version)}（重蒸馏前的版本），此操作会追加一条回滚记录，且不可再次撤销。`
                : '此技能没有可回滚的重蒸馏记录。'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmRollback(false)} disabled={rollbackSkill.isPending}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={() => void handleRollback()}
              disabled={rollbackSkill.isPending || !rollbackTarget}
            >
              {rollbackSkill.isPending ? '正在回滚…' : '确认回滚'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  )
}
