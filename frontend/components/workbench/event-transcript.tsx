import { CircleAlert, Terminal, Wrench, XCircle } from 'lucide-react'

import type { WorkbenchEvent } from '@/lib/api/types'
import { formatDateTime } from '@/lib/format'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

type EventTranscriptProps = {
  events: WorkbenchEvent[] | undefined
  loading: boolean
}

function eventText(event: WorkbenchEvent) {
  const message = event.payload.text ?? event.payload.message ?? event.payload.result
  return typeof message === 'string' ? message : JSON.stringify(event.payload, null, 2)
}

function EventIcon({ eventType }: Pick<WorkbenchEvent, 'eventType'>) {
  if (eventType === 'tool_call' || eventType === 'tool_result') return <Wrench className="size-3.5" />
  if (eventType === 'error') return <XCircle className="size-3.5 text-destructive" />
  if (eventType === 'state') return <CircleAlert className="size-3.5" />
  return <Terminal className="size-3.5" />
}

export function EventTranscript({ events, loading }: EventTranscriptProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Terminal className="size-4" />
          实时持久事件
        </CardTitle>
        <CardDescription>
          先回放服务端序列，再以 <code>Last-Event-ID</code> 续接；重复序列会被丢弃。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-sm text-muted-foreground">正在回放事件…</p> : null}
        {!loading && events?.length ? (
          <ol className="space-y-2" aria-live="polite">
            {events.map((event) => (
              <li key={event.sequence} className="rounded-md border bg-muted/20 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-xs font-medium">
                    <EventIcon eventType={event.eventType} />
                    {event.eventType} · #{event.sequence}
                  </span>
                  <time className="text-xs text-muted-foreground">{formatDateTime(event.createdAt)}</time>
                </div>
                <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">
                  {eventText(event)}
                </pre>
              </li>
            ))}
          </ol>
        ) : null}
        {!loading && !events?.length ? <p className="text-sm text-muted-foreground">此回合尚无持久事件。</p> : null}
      </CardContent>
    </Card>
  )
}
