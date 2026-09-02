import type { WorkbenchEvent } from '@/lib/api/types'

export type WorkbenchStreamState = {
  turnId: string
  status: string
}

type StreamCallbacks = {
  onEvent: (event: WorkbenchEvent) => void
  onState: (state: WorkbenchStreamState) => void
}

/** Keep React Query's durable event cache ordered and reconnect-safe. */
export function mergeWorkbenchEvents(
  current: WorkbenchEvent[] | undefined,
  incoming: WorkbenchEvent,
): WorkbenchEvent[] {
  const known = new Map((current ?? []).map((event) => [event.sequence, event]))
  known.set(incoming.sequence, incoming)
  return [...known.values()].sort((left, right) => left.sequence - right.sequence)
}

/** Consume complete SSE frames and return the incomplete suffix for the next chunk. */
export function consumeWorkbenchSse(chunk: string, callbacks: StreamCallbacks): string {
  const normalized = chunk.replace(/\r\n/g, '\n')
  const frames = normalized.split('\n\n')
  const remainder = frames.pop() ?? ''
  for (const frame of frames) {
    let eventName = 'message'
    const data: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice('event:'.length).trim()
      if (line.startsWith('data:')) data.push(line.slice('data:'.length).trimStart())
    }
    if (data.length === 0) continue
    try {
      const decoded = JSON.parse(data.join('\n')) as unknown
      if (eventName === 'workbench_event' && isWorkbenchEvent(decoded)) callbacks.onEvent(decoded)
      if (eventName === 'turn_state' && isWorkbenchStreamState(decoded)) callbacks.onState(decoded)
    } catch {
      // A malformed frame is ignored; reconnect replay remains authoritative.
    }
  }
  return remainder
}

export async function streamWorkbenchEvents(
  path: string,
  afterSequence: number,
  callbacks: StreamCallbacks,
  headers: HeadersInit,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/v1${path}`, {
    headers: {
      ...headers,
      Accept: 'text/event-stream',
      'Last-Event-ID': String(afterSequence),
    },
    signal,
  })
  if (!response.ok || response.body === null) {
    throw new Error(`Workbench event stream failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let remainder = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      remainder = consumeWorkbenchSse(remainder + decoder.decode(value, { stream: true }), callbacks)
    }
    if (remainder) consumeWorkbenchSse(`${remainder}\n\n`, callbacks)
  } finally {
    reader.releaseLock()
  }
}

function isWorkbenchEvent(value: unknown): value is WorkbenchEvent {
  if (!value || typeof value !== 'object') return false
  const event = value as Partial<WorkbenchEvent>
  return typeof event.id === 'string'
    && typeof event.sequence === 'number'
    && typeof event.eventType === 'string'
    && !!event.payload
    && typeof event.createdAt === 'string'
}

function isWorkbenchStreamState(value: unknown): value is WorkbenchStreamState {
  if (!value || typeof value !== 'object') return false
  const state = value as Partial<WorkbenchStreamState>
  return typeof state.turnId === 'string' && typeof state.status === 'string'
}
