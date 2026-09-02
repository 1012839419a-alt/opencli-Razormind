'use client'

import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { useState, type ReactNode } from 'react'

import AIApproval, { type AIApprovalOption } from '@/components/smoothui/ai-approval'
import { StatusBadge } from '@/components/shell/status-badge'
import { buttonVariants } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useDecideOperationsApproval } from '@/lib/api/hooks'
import type { ApprovalDecision, OperationsWorkItem } from '@/lib/api/types'

export type QueueDetailItem = {
  id: string
  section: 'blocked' | 'waiting' | 'review'
  eyebrow: string
  title: string
  summary: string
  status: string
  createdAt: string
  href: string
  hrefLabel: string
  sourceId?: string
  sourceName?: string
  occurrenceCount: number
  detailLabel: string
  detailValue: string
  approval?: OperationsWorkItem
}

export type QueueSectionMeta = {
  label: string
  icon: ReactNode
  iconTone: string
}

function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}…` : value
}

export function QueueDetail({
  createdAtLabel,
  item,
  meta,
}: {
  createdAtLabel: string
  item: QueueDetailItem
  meta: QueueSectionMeta
}) {
  const nextStep = {
    blocked: '先检查错误和运行参数，再决定是否重新触发采集。',
    waiting: '确认执行容量或通知目标状态，避免事项长期停留在队列。',
    review: '观察后续运行是否恢复，并在控制证据中完成结果判断。',
  }[item.section]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-16 items-start justify-between gap-4 border-b px-5 py-3.5">
        <div className="flex min-w-0 items-start gap-3">
          <span className={`grid size-8 shrink-0 place-items-center rounded-md ${meta.iconTone}`}>
            {meta.icon}
          </span>
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{item.eyebrow}</p>
            <h2 className="mt-0.5 truncate text-base font-semibold leading-tight">{item.title}</h2>
          </div>
        </div>
        <StatusBadge status={item.status} className="shrink-0" />
      </div>

      <ScrollArea data-testid="inbox-detail-scroll" className="min-h-0 flex-1">
        <div className="mx-auto w-full max-w-3xl space-y-7 p-5 lg:p-7">
          <section aria-labelledby="signal-context-heading">
            <h3 id="signal-context-heading" className="text-xs font-medium text-muted-foreground">
              信号上下文
            </h3>
            <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-6 text-foreground/90">
              {item.summary}
            </p>
            {item.occurrenceCount > 1 ? (
              <p className="mt-4 border-l-2 border-border pl-3 text-xs leading-5 text-muted-foreground">
                已将 {item.occurrenceCount} 条同一对象、同一处理阶段的信号合并为一个主题，当前展示最近一次上下文。
              </p>
            ) : null}
          </section>

          <section aria-labelledby="signal-facts-heading">
            <h3 id="signal-facts-heading" className="text-xs font-medium text-muted-foreground">
              关键信息
            </h3>
            <dl className="mt-3 divide-y border-y text-sm">
              <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2.5">
                <dt className="text-muted-foreground">队列</dt>
                <dd>{meta.label}</dd>
              </div>
              <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2.5">
                <dt className="text-muted-foreground">{item.detailLabel}</dt>
                <dd className="break-words">{item.detailValue}</dd>
              </div>
              {item.sourceId ? (
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2.5">
                  <dt className="text-muted-foreground">数据源</dt>
                  <dd>
                    <Link
                      href={`/sources/${item.sourceId}`}
                      className="inline-flex items-center gap-1 font-medium hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {item.sourceName ?? shortId(item.sourceId)}
                      <ArrowUpRight aria-hidden="true" className="size-3.5 text-muted-foreground" />
                    </Link>
                  </dd>
                </div>
              ) : null}
              <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2.5">
                <dt className="text-muted-foreground">最近发生</dt>
                <dd>{createdAtLabel}</dd>
              </div>
            </dl>
          </section>

          <section aria-labelledby="signal-next-step-heading">
            <h3 id="signal-next-step-heading" className="text-xs font-medium text-muted-foreground">
              建议下一步
            </h3>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{nextStep}</p>
          </section>
        </div>
      </ScrollArea>

      <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-t px-5 py-2.5">
        <span className="hidden text-xs text-muted-foreground sm:inline">
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">J</kbd>
          <kbd className="ml-1 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">K</kbd>
          <span className="ml-2">切换</span>
          <kbd className="ml-3 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">Enter</kbd>
          <span className="ml-2">打开</span>
        </span>
        <Link href={item.href} className={buttonVariants({ size: 'sm' })}>
          {item.hrefLabel}
          <ArrowUpRight aria-hidden="true" className="size-3.5" />
        </Link>
      </div>
    </div>
  )
}

const APPROVAL_OPTIONS: AIApprovalOption[] = [
  { id: 'approve', label: '批准执行', detail: '进入执行队列' },
  { id: 'request_changes', label: '要求修改', detail: '返回提案作者' },
  { id: 'reject', label: '拒绝', detail: '不执行此提案', destructive: true },
]

export function ApprovalQueueDetail({ item }: { item: QueueDetailItem }) {
  const decision = useDecideOperationsApproval()
  const [reason, setReason] = useState('')
  const [decisionError, setDecisionError] = useState<string | null>(null)
  const [cardRevision, setCardRevision] = useState(0)
  const approval = item.approval

  async function decideApproval(option: AIApprovalOption) {
    if (!approval || !reason.trim() || decision.isPending) return
    setDecisionError(null)
    try {
      await decision.mutateAsync({
        workspaceId: approval.workspace_id,
        approvalId: approval.id,
        decision: option.id as ApprovalDecision,
        reason: reason.trim(),
      })
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : '审批决定提交失败')
      setCardRevision((revision) => revision + 1)
    }
  }

  if (!approval) return null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-16 items-start justify-between gap-4 border-b px-5 py-3.5">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{item.eyebrow}</p>
          <h2 className="mt-0.5 truncate text-base font-semibold leading-tight">{item.title}</h2>
        </div>
        <StatusBadge status={item.status} className="shrink-0" />
      </div>

      <ScrollArea data-testid="inbox-detail-scroll" className="min-h-0 flex-1">
        <div className="mx-auto w-full max-w-3xl space-y-5 p-5 lg:p-7">
          <label className="block space-y-2">
            <span className="text-xs font-medium text-muted-foreground">审批理由（必填）</span>
            <input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="说明批准、拒绝或要求修改的依据"
              aria-describedby="approval-reason-hint"
              disabled={decision.isPending}
              className="h-9 w-full rounded-md border bg-transparent px-3 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span id="approval-reason-hint" className="block text-[11px] text-muted-foreground">
              理由会随决定写入审计记录。
            </span>
          </label>

          <AIApproval
            key={`${approval.id}-${cardRevision}`}
            question={item.title}
            options={APPROVAL_OPTIONS}
            disabled={!reason.trim()}
            pending={decision.isPending}
            onDecide={(option) => void decideApproval(option)}
          >
            <p>{item.summary}</p>
            <p className="mt-1">
              {item.detailLabel}：{item.detailValue} · Workspace：{item.sourceName}
            </p>
          </AIApproval>

          {decisionError ? (
            <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {decisionError}。决定尚未生效，请检查连接后重试。
            </p>
          ) : null}

          {Object.keys(approval.evidence).length ? (
            <details className="rounded-lg border bg-background">
              <summary className="cursor-pointer px-3 py-2 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                查看原始审批证据
              </summary>
              <pre className="max-h-72 overflow-auto border-t p-3 font-mono text-[10px] leading-4">
                {JSON.stringify(approval.evidence, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      </ScrollArea>

      <div className="flex min-h-14 items-center justify-end border-t px-5 py-2.5">
        <Link href="/operations-agents" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          打开智能体
          <ArrowUpRight aria-hidden="true" className="size-3.5" />
        </Link>
      </div>
    </div>
  )
}
