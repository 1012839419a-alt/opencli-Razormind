export type OperationsTaskStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'blocked'
  | 'partial'

export type OperationsNodeState = {
  nodeId: string
  status: string
  eventCount: number
}

export type OperationsNodeTask = {
  id: string
  label: string
  note: string
  status: OperationsTaskStatus
}

export function toOperationsTaskStatus(status: string): OperationsTaskStatus {
  if (status === 'completed') return 'done'
  if (status === 'failed') return 'failed'
  if (status === 'blocked') return 'blocked'
  if (status === 'partial' || status === 'partial_success') return 'partial'
  if (status === 'running') return 'running'
  return 'pending'
}

export function buildOperationsNodeTasks(
  nodeStates: OperationsNodeState[],
): OperationsNodeTask[] {
  return nodeStates.map((node) => ({
    id: node.nodeId,
    label: node.nodeId,
    note: `${node.eventCount} events · ${node.status}`,
    status: toOperationsTaskStatus(node.status),
  }))
}
