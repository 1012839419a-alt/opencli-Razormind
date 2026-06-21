import type {
  AIAgent,
  CollectedRecord,
  CollectionTask,
  CronSchedule,
  DataSource,
  EdgeNode,
  NotificationLog,
  NotificationRule,
  WorkerNode,
} from '../api/types'

export type TopologyKind =
  | 'source'
  | 'schedule'
  | 'task'
  | 'agent'
  | 'record'
  | 'notification'
  | 'edge-node'
  | 'worker'

export type TopologyHealth =
  | 'healthy'
  | 'active'
  | 'warning'
  | 'failed'
  | 'disabled'
  | 'unknown'

export interface TopologyNodeData extends Record<string, unknown> {
  kind: TopologyKind
  title: string
  subtitle: string
  health: TopologyHealth
  badges: string[]
  targetPath?: string
  detail: Record<string, unknown>
}

interface TopologyNodeBody {
  title: string
  subtitle: string
  health: TopologyHealth
  badges: string[]
  targetPath?: string
  detail: Record<string, unknown>
}

export interface TopologyGraphNode {
  id: string
  column: number
  row: number
  data: TopologyNodeData
}

export interface TopologyGraphEdge {
  id: string
  source: string
  target: string
  label?: string
  health: TopologyHealth
}

export interface TopologyGraph {
  nodes: TopologyGraphNode[]
  edges: TopologyGraphEdge[]
  summary: {
    total: number
    failed: number
    warning: number
    active: number
    disabled: number
  }
}

export interface TopologyInput {
  sources: DataSource[]
  schedules?: CronSchedule[]
  tasks: CollectionTask[]
  agents: AIAgent[]
  records: CollectedRecord[]
  notificationRules: NotificationRule[]
  notificationLogs: NotificationLog[]
  edgeNodes: EdgeNode[]
  workers: WorkerNode[]
}

export interface TopologyOptions {
  maxRecords?: number
  maxNotifications?: number
}

const KIND_COLUMN: Record<TopologyKind, number> = {
  source: 0,
  schedule: 1,
  task: 2,
  agent: 3,
  record: 4,
  notification: 5,
  'edge-node': 2,
  worker: 3,
}

export function buildTopologyGraph(input: TopologyInput, options: TopologyOptions = {}): TopologyGraph {
  const maxRecords = options.maxRecords ?? 18
  const maxNotifications = options.maxNotifications ?? 20
  const nodes: TopologyGraphNode[] = []
  const edges: TopologyGraphEdge[] = []
  const seenNodes = new Set<string>()
  const seenEdges = new Set<string>()
  const rowsByColumn = new Map<number, number>()

  const addNode = (kind: TopologyKind, rawId: string, data: TopologyNodeBody) => {
    const id = nodeId(kind, rawId)
    if (seenNodes.has(id)) return id

    const column = KIND_COLUMN[kind]
    const row = rowsByColumn.get(column) ?? 0
    rowsByColumn.set(column, row + 1)
    nodes.push({ id, column, row, data: { ...data, kind } })
    seenNodes.add(id)
    return id
  }

  const addEdge = (source: string | undefined, target: string | undefined, label?: string, health: TopologyHealth = 'unknown') => {
    if (!source || !target || source === target) return
    if (!seenNodes.has(source) || !seenNodes.has(target)) return
    const id = `${source}->${target}${label ? `:${label}` : ''}`
    if (seenEdges.has(id)) return
    edges.push({ id, source, target, label, health })
    seenEdges.add(id)
  }

  for (const source of input.sources) {
    addNode('source', source.id, {
      title: source.name,
      subtitle: source.channel_type,
      health: source.enabled ? 'healthy' : 'disabled',
      badges: compact([source.enabled ? 'enabled' : 'disabled', ...source.tags.slice(0, 2)]),
      targetPath: '/sources',
      detail: {
        id: source.id,
        channel: source.channel_type,
        updated_at: source.updated_at,
      },
    })
  }

  for (const schedule of input.schedules ?? []) {
    const scheduleNode = addNode('schedule', schedule.id, {
      title: schedule.name,
      subtitle: schedule.cron_expression,
      health: healthFromSchedule(schedule),
      badges: compact([
        schedule.enabled ? 'enabled' : 'disabled',
        schedule.timezone,
        schedule.next_run_at ? `next ${shortDate(schedule.next_run_at)}` : undefined,
      ]),
      targetPath: `/schedules?source_id=${encodeURIComponent(schedule.source_id)}`,
      detail: {
        id: schedule.id,
        source_id: schedule.source_id,
        agent_id: schedule.agent_id,
        cron_expression: schedule.cron_expression,
        timezone: schedule.timezone,
        enabled: schedule.enabled,
        is_one_time: schedule.is_one_time,
        next_run_at: schedule.next_run_at,
        last_run_at: schedule.last_run_at,
        updated_at: schedule.updated_at,
      },
    })
    addEdge(nodeId('source', schedule.source_id), scheduleNode, 'plans', healthFromSchedule(schedule))
  }

  for (const task of input.tasks) {
    const taskNode = addNode('task', task.id, {
      title: task.source_name || `Task ${shortId(task.id)}`,
      subtitle: task.trigger_type,
      health: healthFromTaskStatus(task.status),
      badges: compact([task.status, `P${task.priority}`]),
      targetPath: '/tasks',
      detail: {
        id: task.id,
        source_id: task.source_id,
        agent_id: task.agent_id,
        status: task.status,
        updated_at: task.updated_at,
        error: task.error_message,
      },
    })
    addEdge(nodeId('source', task.source_id), taskNode, 'triggers', healthFromTaskStatus(task.status))
  }

  for (const agent of input.agents) {
    addNode('agent', agent.id, {
      title: agent.name,
      subtitle: agent.model || agent.processor_type,
      health: agent.enabled ? 'healthy' : 'disabled',
      badges: compact([agent.enabled ? 'enabled' : 'disabled', agent.processor_type]),
      targetPath: '/agents',
      detail: {
        id: agent.id,
        processor_type: agent.processor_type,
        provider_id: agent.provider_id,
        updated_at: agent.updated_at,
      },
    })
  }

  for (const task of input.tasks) {
    addEdge(
      nodeId('task', task.id),
      task.agent_id ? nodeId('agent', task.agent_id) : undefined,
      'enriches',
      healthFromTaskStatus(task.status),
    )
  }

  const sampledRecords = [...input.records]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, maxRecords)

  for (const record of sampledRecords) {
    const title = readRecordTitle(record) || `Record ${shortId(record.id)}`
    const recordNode = addNode('record', record.id, {
      title,
      subtitle: record.status,
      health: healthFromRecordStatus(record.status),
      badges: compact([record.status, shortId(record.content_hash)]),
      targetPath: '/records',
      detail: {
        id: record.id,
        source_id: record.source_id,
        task_id: record.task_id,
        status: record.status,
        created_at: record.created_at,
        error: record.error_message,
      },
    })
    addEdge(nodeId('task', record.task_id), recordNode, 'writes', healthFromRecordStatus(record.status))
    addEdge(nodeId('source', record.source_id), recordNode, 'collects', healthFromRecordStatus(record.status))
  }

  const logsByRule = groupBy(input.notificationLogs, (log) => log.rule_id)
  const logsByRecord = groupBy(input.notificationLogs, (log) => log.record_id || '')

  for (const rule of input.notificationRules.slice(0, maxNotifications)) {
    const ruleLogs = logsByRule.get(rule.id) ?? []
    const notificationNode = addNode('notification', rule.id, {
      title: rule.name,
      subtitle: rule.notifier_type,
      health: healthFromNotification(rule, ruleLogs),
      badges: compact([rule.enabled ? 'enabled' : 'disabled', rule.trigger_event]),
      targetPath: '/notifications',
      detail: {
        id: rule.id,
        source_id: rule.source_id,
        trigger_event: rule.trigger_event,
        notifier_type: rule.notifier_type,
        recent_logs: ruleLogs.length,
      },
    })
    addEdge(rule.source_id ? nodeId('source', rule.source_id) : undefined, notificationNode, 'notifies', healthFromNotification(rule, ruleLogs))
  }

  for (const record of sampledRecords) {
    const recordLogs = logsByRecord.get(record.id) ?? []
    for (const log of recordLogs) {
      addEdge(
        nodeId('record', record.id),
        nodeId('notification', log.rule_id),
        log.ack_status === 'acked' ? 'acked' : 'sent',
        healthFromNotificationLog(log),
      )
    }
  }

  for (const node of input.edgeNodes) {
    addNode('edge-node', node.id, {
      title: node.label || node.url,
      subtitle: `${node.protocol.toUpperCase()} · ${node.mode}`,
      health: node.status === 'online' ? 'healthy' : 'failed',
      badges: compact([node.node_type, node.status]),
      targetPath: '/nodes',
      detail: {
        id: node.id,
        url: node.url,
        ip: node.ip,
        last_seen_at: node.last_seen_at,
      },
    })
  }

  for (const worker of input.workers) {
    addNode('worker', worker.id, {
      title: worker.hostname || worker.worker_id,
      subtitle: worker.worker_id,
      health: healthFromWorker(worker),
      badges: compact([worker.status, `${worker.active_tasks} active`]),
      targetPath: '/workers',
      detail: {
        id: worker.id,
        worker_id: worker.worker_id,
        active_tasks: worker.active_tasks,
        last_heartbeat: worker.last_heartbeat,
      },
    })
  }

  const summary = nodes.reduce(
    (acc, node) => ({
      total: acc.total + 1,
      failed: acc.failed + (node.data.health === 'failed' ? 1 : 0),
      warning: acc.warning + (node.data.health === 'warning' ? 1 : 0),
      active: acc.active + (node.data.health === 'active' ? 1 : 0),
      disabled: acc.disabled + (node.data.health === 'disabled' ? 1 : 0),
    }),
    { total: 0, failed: 0, warning: 0, active: 0, disabled: 0 },
  )

  return { nodes, edges, summary }
}

export function fallbackLayout(graph: TopologyGraph, columnGap = 280, rowGap = 136) {
  return graph.nodes.map((node) => ({
    ...node,
    position: {
      x: node.column * columnGap,
      y: node.row * rowGap,
    },
  }))
}

export function nodeId(kind: TopologyKind, rawId: string) {
  return `${kind}:${rawId}`
}

export function shortId(value?: string | null, length = 8) {
  return value ? value.slice(0, length) : ''
}

function healthFromTaskStatus(status: CollectionTask['status']): TopologyHealth {
  if (status === 'failed' || status === 'cancelled') return 'failed'
  if (status === 'running') return 'active'
  if (status === 'pending') return 'warning'
  return 'healthy'
}

function healthFromSchedule(schedule: CronSchedule): TopologyHealth {
  if (!schedule.enabled) return 'disabled'
  if (!schedule.next_run_at && !schedule.is_one_time) return 'warning'
  return 'healthy'
}

function healthFromRecordStatus(status: string): TopologyHealth {
  if (status === 'error' || status === 'failed') return 'failed'
  if (status === 'raw' || status === 'normalized') return 'warning'
  if (status === 'ai_processed' || status === 'stored') return 'healthy'
  return 'unknown'
}

function healthFromNotification(rule: NotificationRule, logs: NotificationLog[]): TopologyHealth {
  if (!rule.enabled) return 'disabled'
  if (logs.some((log) => log.status === 'failed' || log.ack_status === 'failed')) return 'failed'
  if (logs.some((log) => log.ack_status === 'pending')) return 'warning'
  return 'healthy'
}

function healthFromNotificationLog(log: NotificationLog): TopologyHealth {
  if (log.status === 'failed' || log.ack_status === 'failed') return 'failed'
  if (log.ack_status === 'pending') return 'warning'
  if (log.ack_status === 'acked') return 'healthy'
  return 'unknown'
}

function healthFromWorker(worker: WorkerNode): TopologyHealth {
  const status = worker.status.toLowerCase()
  if (status.includes('offline') || status.includes('failed') || status.includes('error')) return 'failed'
  if (worker.active_tasks > 0 || status.includes('busy') || status.includes('active')) return 'active'
  if (status.includes('starting') || status.includes('pending')) return 'warning'
  return 'healthy'
}

function readRecordTitle(record: CollectedRecord) {
  const candidates = [
    record.normalized_data.title,
    record.raw_data.title,
    record.normalized_data.url,
    record.raw_data.url,
  ]
  return candidates.find((value): value is string => typeof value === 'string' && value.trim().length > 0)?.trim()
}

function shortDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function groupBy<T>(items: T[], keyFn: (item: T) => string) {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const key = keyFn(item)
    if (!key) continue
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return groups
}

function compact(items: Array<string | undefined | null | false>) {
  return items.filter((item): item is string => typeof item === 'string' && item.length > 0)
}
