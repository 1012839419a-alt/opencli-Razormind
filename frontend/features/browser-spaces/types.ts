export type BrowserSpaceStatus = 'idle' | 'running' | 'closed' | 'error'
export type BrowserSpaceTaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type BrowserSpaceEventKind = 'queued' | 'started' | 'completed' | 'failed' | 'cancel_requested' | 'cancelled'

export interface BrowserSpaceInstanceOption {
  id: string
  label: string
  mode?: string | null
  binding_id?: string | null
  granted_capabilities?: string[]
}

export interface BrowserSpaceTask {
  id: string
  operation_id: string
  capability: string
  status: BrowserSpaceTaskStatus
  result?: Record<string, unknown> | null
  error?: { code?: string; message?: string } | null
  error_code?: string | null
  error_message?: string | null
  created_at?: string | null
  finished_at?: string | null
}

export interface BrowserSpace {
  id: string
  workspace_id: string
  browser_instance_id: string
  binding_id?: string | null
  owner_type: 'operator' | 'runtime_agent'
  owner_id: string
  status: BrowserSpaceStatus
  granted_capabilities: string[]
  last_error_code?: string | null
  updated_at?: string | null
  latest_task?: BrowserSpaceTask | null
}

export interface BrowserSpaceEvent {
  id: string
  sequence: number
  kind: BrowserSpaceEventKind
  payload?: Record<string, unknown> | null
  created_at: string
}

export interface BrowserSpaceList {
  spaces: BrowserSpace[]
  // The #90 backend may include this field on the list response. Keeping it
  // optional means an older backend safely renders a read-only panel.
  available_instances?: BrowserSpaceInstanceOption[]
}

export interface CreateBrowserSpaceInput {
  browser_instance_id: string
  binding_id?: string
  owner_type: 'operator' | 'runtime_agent'
  owner_id: string
  granted_capabilities: string[]
}

export interface SubmitBrowserSpaceTaskInput {
  request_id: string
  capability: string
  args: Record<string, unknown>
  timeout_seconds: number
}
