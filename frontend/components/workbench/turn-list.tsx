import { Square } from 'lucide-react'

import type { WorkbenchThread, WorkbenchTurn } from '@/lib/api/types'
import { formatDateTime } from '@/lib/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export const TURN_STATUS_LABEL: Record<WorkbenchTurn['status'], string> = {
  queued: '已排队',
  running: '运行中',
  proposed: '待确认',
  applied: '已应用',
  failed: '失败',
  cancelled: '已取消',
}

const TURN_STATUS_CLASS: Record<WorkbenchTurn['status'], string> = {
  queued: 'border-border bg-muted text-muted-foreground',
  running: 'border-border bg-muted text-muted-foreground',
  proposed: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  applied: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  failed: 'border-destructive/40 bg-destructive/10 text-destructive',
  cancelled: 'border-border bg-muted text-muted-foreground',
}

type TurnListProps = {
  thread: WorkbenchThread
  currentTurnId: string | null
  cancelling: boolean
  onSelect: (turn: WorkbenchTurn) => void
  onCancel: (turn: WorkbenchTurn) => void
}

export function TurnList({ thread, currentTurnId, cancelling, onSelect, onCancel }: TurnListProps) {
  const turns = [...thread.turns].sort((left, right) => left.sequence - right.sequence)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">持久回合</CardTitle>
        <CardDescription>运行时版本和基础 SHA 均由服务端在提交时固定。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {turns.map((turn) => (
          <article
            key={turn.id}
            className={`rounded-md border p-3 ${turn.id === currentTurnId ? 'border-primary/50 bg-primary/5' : ''}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <button type="button" className="min-w-0 text-left" onClick={() => onSelect(turn)}>
                <p className="text-sm font-medium">#{turn.sequence} · {turn.requirement}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {turn.runtimeType} · v{turn.publishedVersion} · {turn.baseSha.slice(0, 12)} · {formatDateTime(turn.createdAt)}
                </p>
              </button>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={TURN_STATUS_CLASS[turn.status]}>
                  {TURN_STATUS_LABEL[turn.status]}
                </Badge>
                {turn.status === 'queued' || turn.status === 'running' ? (
                  <Button size="sm" variant="outline" onClick={() => onCancel(turn)} disabled={cancelling}>
                    <Square className="size-3.5" />
                    取消
                  </Button>
                ) : null}
              </div>
            </div>
            {turn.errorMessage ? <p role="alert" className="mt-2 text-sm text-destructive">{turn.errorMessage}</p> : null}
          </article>
        ))}
      </CardContent>
    </Card>
  )
}
