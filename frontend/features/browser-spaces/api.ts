import { apiClient } from '@/lib/api/client'

import type {
  BrowserSpace,
  BrowserSpaceEvent,
  BrowserSpaceList,
  CreateBrowserSpaceInput,
  SubmitBrowserSpaceTaskInput,
} from './types'

type ApiResponse<T> = { data: T }
type BrowserSpaceWire = Omit<BrowserSpace, 'id'> & { space_id: string }
type BrowserSpaceListWire = Omit<BrowserSpaceList, 'spaces'> & { spaces: BrowserSpaceWire[] }
type BrowserSpaceEventWire = Omit<BrowserSpaceEvent, 'id'>

const base = (workspaceId: string) => `/workspaces/${encodeURIComponent(workspaceId)}/browser-spaces`

const toBrowserSpace = ({ space_id, ...space }: BrowserSpaceWire): BrowserSpace => ({ id: space_id, ...space })

const toBrowserSpaceList = (data: BrowserSpaceWire[] | BrowserSpaceListWire): BrowserSpaceList =>
  Array.isArray(data)
    ? { spaces: data.map(toBrowserSpace) }
    : { ...data, spaces: data.spaces.map(toBrowserSpace) }

const toBrowserSpaceEvent = (event: BrowserSpaceEventWire): BrowserSpaceEvent => ({
  ...event,
  id: `${event.sequence}`,
})

export async function listBrowserSpaces(workspaceId: string): Promise<BrowserSpaceList> {
  const response = await apiClient.get<ApiResponse<BrowserSpaceWire[] | BrowserSpaceListWire>>(base(workspaceId), { params: { limit: 20 } })
  return toBrowserSpaceList(response.data.data)
}

export const createBrowserSpace = (workspaceId: string, data: CreateBrowserSpaceInput) =>
  apiClient.post<ApiResponse<BrowserSpaceWire>>(base(workspaceId), data).then((response) => toBrowserSpace(response.data.data))

export const submitBrowserSpaceTask = (workspaceId: string, spaceId: string, data: SubmitBrowserSpaceTaskInput) =>
  apiClient.post<ApiResponse<BrowserSpaceTaskResult>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/tasks`, data).then((response) => response.data.data)

export const cancelBrowserSpaceTask = (workspaceId: string, spaceId: string) =>
  apiClient.post<ApiResponse<BrowserSpaceTaskResult>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/cancel`, {}).then((response) => response.data.data)

export const closeBrowserSpace = (workspaceId: string, spaceId: string) =>
  apiClient.post<ApiResponse<BrowserSpaceWire>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/close`, {}).then((response) => toBrowserSpace(response.data.data))

export const listBrowserSpaceEvents = (workspaceId: string, spaceId: string) =>
  apiClient.get<ApiResponse<BrowserSpaceEventWire[]>>(`${base(workspaceId)}/${encodeURIComponent(spaceId)}/events`, {
    params: { after_sequence: 0, limit: 100 },
  }).then((response) => response.data.data.map(toBrowserSpaceEvent))

export interface BrowserSpaceTaskResult {
  task_id: string
  operation_id: string
  status: string
  result?: Record<string, unknown> | null
  error?: { code?: string; message?: string } | null
}
