import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import * as api from './api'

const key = (workspaceId: string) => ['browser-spaces', workspaceId] as const

export function useBrowserSpaces(workspaceId: string | null) {
  return useQuery({
    queryKey: key(workspaceId ?? ''),
    queryFn: () => api.listBrowserSpaces(workspaceId as string),
    enabled: Boolean(workspaceId),
    refetchInterval: 5_000,
  })
}

export function useBrowserSpaceEvents(workspaceId: string | null, spaceId: string | null) {
  return useQuery({
    queryKey: ['browser-space-events', workspaceId, spaceId],
    queryFn: () => api.listBrowserSpaceEvents(workspaceId as string, spaceId as string),
    enabled: Boolean(workspaceId && spaceId),
    refetchInterval: 5_000,
  })
}

export function useBrowserSpaceActions() {
  const queryClient = useQueryClient()
  const refresh = (workspaceId: string, spaceId?: string) => {
    void queryClient.invalidateQueries({ queryKey: key(workspaceId) })
    if (spaceId) void queryClient.invalidateQueries({ queryKey: ['browser-space-events', workspaceId, spaceId] })
  }

  return {
    create: useMutation({
      mutationFn: ({ workspaceId, data }: { workspaceId: string; data: Parameters<typeof api.createBrowserSpace>[1] }) => api.createBrowserSpace(workspaceId, data),
      onSuccess: (_result, { workspaceId }) => refresh(workspaceId),
    }),
    submit: useMutation({
      mutationFn: ({ workspaceId, spaceId, data }: { workspaceId: string; spaceId: string; data: Parameters<typeof api.submitBrowserSpaceTask>[2] }) => api.submitBrowserSpaceTask(workspaceId, spaceId, data),
      onSuccess: (_result, { workspaceId, spaceId }) => refresh(workspaceId, spaceId),
    }),
    cancel: useMutation({
      mutationFn: ({ workspaceId, spaceId }: { workspaceId: string; spaceId: string }) => api.cancelBrowserSpaceTask(workspaceId, spaceId),
      onSuccess: (_result, { workspaceId, spaceId }) => refresh(workspaceId, spaceId),
    }),
    close: useMutation({
      mutationFn: ({ workspaceId, spaceId }: { workspaceId: string; spaceId: string }) => api.closeBrowserSpace(workspaceId, spaceId),
      onSuccess: (_result, { workspaceId, spaceId }) => refresh(workspaceId, spaceId),
    }),
  }
}
