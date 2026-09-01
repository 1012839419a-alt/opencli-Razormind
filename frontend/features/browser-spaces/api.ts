import { apiClient } from '@/lib/api/client'

import type {
  BrowserSpace,
  BrowserSpaceEvent,
  BrowserSpaceList,
  CreateBrowserSpaceInput,
  SubmitBrowserSpaceTaskInput,
} from './types'

type ApiResponse<T> = { data: T }

const base = (workspaceId: string) => `/workspaces/${encodeURIComponent(workspaceId)}/browser-spaces`

export async function listBrowserSpaces(workspaceId: string): Promise<BrowserSpaceList> {
  const response = await apiClient.get<ApiResponse<BrowserSpace[] | BrowserSpaceList>>(base(workspaceId), { params: { limit: 20 } })
  const data = response.data.data
  return Array.isArray(data) ? { spaces: data } : data
}

export const createBrowserSpace = (workspaceId: string, data: CreateBrowserSpaceInput) =>
  apiClient.post<ApiResponse<BrowserSpace>>(base(workspaceId), data).then((response) => response.data.data)

export const submitBrowserSpaceTask = (workspaceId: string, spaceId: string, data: SubmitBrowserSpaceTaskInput) =>
  apiClient.post<ApiResponse<BrowserSpaceTaskResult>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/tasks`, data).then((response) => response.data.data)

export const cancelBrowserSpaceTask = (workspaceId: string, spaceId: string) =>
  apiClient.post<ApiResponse<BrowserSpaceTaskResult>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/cancel`, {}).then((response) => response.data.data)

export const closeBrowserSpace = (workspaceId: string, spaceId: string) =>
  apiClient.post<ApiResponse<BrowserSpace>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/close`, {}).then((response) => response.data.data)

export const listBrowserSpaceEvents = (workspaceId: string, spaceId: string) =>
  apiClient.get<ApiResponse<BrowserSpaceEvent[]>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/events`, {
    params: { after_sequence: 0, limit: 100 },
  }).then((response) => response.data.data)

export interface BrowserSpaceTaskResult {
  task_id: string
  operation_id: string
  status: string
  result?: Record<string, unknown> | null
  error?: { code?: string; message?: string } | null
}
