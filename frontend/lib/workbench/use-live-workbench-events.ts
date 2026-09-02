'use client'

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { getApiAuthHeaders } from '@/lib/api/auth-headers'
import { workbenchEventStreamUrl } from '@/lib/api/endpoints'
import type { WorkbenchEvent } from '@/lib/api/types'
import { mergeWorkbenchEvents, streamWorkbenchEvents } from '@/lib/workbench/events'

const TERMINAL_TURN_STATUSES: Record<string, true> = {
  proposed: true,
  applied: true,
  failed: true,
  cancelled: true,
}

export function useLiveWorkbenchEvents(
  workspaceId: string | null,
  threadId: string | null,
  turnId: string | null,
  replay: WorkbenchEvent[] | undefined,
  replayReady: boolean,
) {
  const queryClient = useQueryClient()
  const lastSequenceRef = useRef(0)

  useEffect(() => {
    lastSequenceRef.current = 0
  }, [workspaceId, threadId, turnId])

  useEffect(() => {
    lastSequenceRef.current = Math.max(
      lastSequenceRef.current,
      ...(replay?.map((event) => event.sequence) ?? [0]),
    )
  }, [replay])

  useEffect(() => {
    if (!workspaceId || !threadId || !turnId || !replayReady) return

    const controller = new AbortController()
    let retryTimer: number | undefined
    const connect = async () => {
      let terminal = false
      try {
        await streamWorkbenchEvents(
          workbenchEventStreamUrl(workspaceId, threadId, turnId, lastSequenceRef.current),
          lastSequenceRef.current,
          {
            onEvent: (event) => {
              lastSequenceRef.current = Math.max(lastSequenceRef.current, event.sequence)
              queryClient.setQueryData<WorkbenchEvent[]>(
                ['workbench', workspaceId, 'threads', threadId, 'turns', turnId, 'events'],
                (current) => mergeWorkbenchEvents(current, event),
              )
            },
            onState: (state) => {
              terminal = TERMINAL_TURN_STATUSES[state.status] === true
              void queryClient.invalidateQueries({
                queryKey: ['workbench', workspaceId, 'threads', threadId],
              })
              void queryClient.invalidateQueries({ queryKey: ['workbench', workspaceId, 'threads'] })
            },
          },
          getApiAuthHeaders(),
          controller.signal,
        )
        if (!terminal && !controller.signal.aborted) {
          retryTimer = window.setTimeout(() => void connect(), 750)
        }
      } catch {
        if (!controller.signal.aborted) {
          retryTimer = window.setTimeout(() => void connect(), 750)
        }
      }
    }
    void connect()

    return () => {
      controller.abort()
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [workspaceId, threadId, turnId, replayReady, queryClient])
}
