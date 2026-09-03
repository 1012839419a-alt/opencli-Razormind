'use client'

import type { FormEvent, KeyboardEventHandler, ReactNode } from 'react'
import { Check, CheckCircle2, ChevronDown, CircleAlert, Clock3, Loader2, ShieldCheck, Terminal, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

export type AgentTaskStatus = 'queued' | 'running' | 'completed' | 'failed'

type StatusConfig = {
  label: string
  icon: typeof CheckCircle2
  className: string
}

const statusConfig: Record<AgentTaskStatus, StatusConfig> = {
  queued: { label: '排队中', icon: Clock3, className: 'text-muted-foreground' },
  running: { label: '运行中', icon: Loader2, className: 'text-info' },
  completed: { label: '已完成', icon: CheckCircle2, className: 'text-success' },
  failed: { label: '失败', icon: CircleAlert, className: 'text-destructive' },
}

export function AgentStatusBadge({ status }: { status: AgentTaskStatus }) {
  const config = statusConfig[status]
  const Icon = config.icon

  return (
    <Badge variant="outline" className={cn('gap-1.5 font-normal', config.className)}>
      <Icon className={cn('size-3.5', status === 'running' && 'animate-spin')} aria-hidden />
      {config.label}
    </Badge>
  )
}

export function ToolChip({
  label,
  detail,
  icon: Icon = Terminal,
  tone = 'neutral',
}: {
  label: string
  detail?: string
  icon?: typeof Terminal
  tone?: 'neutral' | 'success' | 'warning'
}) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] leading-none',
        tone === 'success' && 'border-success/30 bg-success/8 text-success',
        tone === 'warning' && 'border-warning/35 bg-warning/10 text-warning-foreground dark:text-warning',
        tone === 'neutral' && 'border-border/80 bg-muted/40 text-muted-foreground',
      )}
    >
      <Icon className="size-3 shrink-0" aria-hidden />
      <span className="truncate font-medium text-foreground/80">{label}</span>
      {detail ? <span className="truncate text-muted-foreground">{detail}</span> : null}
    </span>
  )
}

export function ThinkingTrace({
  label = 'Agent 正在处理',
  steps,
}: {
  label?: string
  steps?: string[]
}) {
  return (
    <details open className="group rounded-lg border border-border/70 bg-muted/20">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-xs text-muted-foreground [&::-webkit-details-marker]:hidden">
        <Loader2 className="size-3.5 animate-spin text-info" aria-hidden />
        <span className="font-medium text-foreground/80">{label}</span>
        {steps?.length ? <span className="text-muted-foreground">· {steps.length} 个步骤</span> : null}
        <ChevronDown className="ml-auto size-3.5 transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      {steps?.length ? (
        <div className="space-y-1.5 border-t border-border/60 px-3 py-2.5">
          {steps.map((step, index) => (
            <div key={step} className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <span className="grid size-4 place-items-center rounded-full bg-background font-mono text-[9px]">{index + 1}</span>
              {step}
            </div>
          ))}
        </div>
      ) : null}
    </details>
  )
}

export function ApprovalCard({
  summary,
  diff,
  metadata,
  confirming = false,
  disabled = false,
  onReject,
  onConfirm,
}: {
  summary: string
  diff: string
  metadata?: Array<{ label: string; value: string }>
  confirming?: boolean
  disabled?: boolean
  onReject: () => void
  onConfirm: () => void
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-warning/35 bg-warning/8" aria-label="待确认操作">
      <div className="flex items-start gap-2.5 border-b border-warning/20 px-3 py-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-warning/15 text-warning">
          <ShieldCheck className="size-3.5" aria-hidden />
        </span>
        <div className="min-w-0">
          <div className="text-sm font-medium">待确认操作</div>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">写入变更先展示提案，确认后才会执行。</p>
        </div>
      </div>
      <div className="space-y-3 p-3">
        <p className="text-sm leading-5">{summary}</p>
        <div className="rounded-lg border border-border/70 bg-background/75 p-2.5 font-mono text-2xs leading-5 whitespace-pre-wrap">
          {diff}
        </div>
        {metadata?.length ? (
          <div className="grid gap-1 font-mono text-3xs text-muted-foreground">
            {metadata.map((item) => (
              <div key={item.label} className="flex justify-between gap-3">
                <span>{item.label}</span>
                <span className="truncate text-right text-foreground/70">{item.value}</span>
              </div>
            ))}
          </div>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" disabled={confirming} onClick={onReject}>
            <X aria-hidden />
            拒绝
          </Button>
          <Button size="sm" disabled={disabled || confirming} onClick={onConfirm}>
            {confirming ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
            确认执行
          </Button>
        </div>
      </div>
    </section>
  )
}

export function AgentTaskRow({
  title,
  detail,
  meta,
  status,
  progress,
}: {
  title: string
  detail?: string
  meta?: string
  status: AgentTaskStatus
  progress?: number
}) {
  return (
    <div className="group rounded-lg border border-border/70 bg-background/55 p-3 transition-colors hover:border-primary/25 hover:bg-muted/30">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-muted/70 text-muted-foreground">
          {status === 'running' ? <Loader2 className="size-3.5 animate-spin text-info" aria-hidden /> : <Terminal className="size-3.5" aria-hidden />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="truncate text-sm font-medium">{title}</p>
            <AgentStatusBadge status={status} />
          </div>
          {detail ? <p className="mt-1 text-xs text-muted-foreground">{detail}</p> : null}
          {meta ? <p className="mt-2 font-mono text-3xs text-muted-foreground">{meta}</p> : null}
          {typeof progress === 'number' ? (
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-muted" aria-label={`进度 ${progress}%`}>
              <div className="h-full rounded-full bg-primary/70 transition-[width]" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function AgentPromptBar({
  value,
  onChange,
  onSubmit,
  onKeyDown,
  disabled = false,
  submitting = false,
  placeholder,
  footer,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onKeyDown: KeyboardEventHandler<HTMLTextAreaElement>
  disabled?: boolean
  submitting?: boolean
  placeholder: string
  footer?: ReactNode
}) {
  return (
    <form className="border-t bg-background/85 p-3 backdrop-blur" onSubmit={onSubmit}>
      <div className="rounded-xl border border-border/80 bg-muted/20 p-2 transition-colors focus-within:border-primary/40 focus-within:bg-background">
        <Textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-label="给全局 Agent 的消息"
          className="max-h-32 min-h-16 resize-none border-0 bg-transparent p-1.5 shadow-none focus-visible:ring-0"
          disabled={disabled}
        />
        <div className="flex items-center justify-between gap-2 px-1.5 pt-2">
          <div className="min-w-0 truncate text-3xs text-muted-foreground">{footer}</div>
          <Button type="submit" size="sm" disabled={!value.trim() || disabled}>
            {submitting ? <Loader2 className="animate-spin" aria-hidden /> : <Terminal aria-hidden />}
            发送
          </Button>
        </div>
      </div>
    </form>
  )
}
