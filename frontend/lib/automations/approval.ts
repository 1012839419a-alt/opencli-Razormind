import type { OperationsAgentMode } from '@/lib/api/types'

export const AUTOMATION_APPROVALS: Array<{
  id: OperationsAgentMode
  label: string
  detail: string
}> = [
  { id: 'observe_only', label: '仅观察', detail: '不提出或执行变更' },
  { id: 'suggest_changes', label: '建议需批准', detail: '送入 Inbox 后由人决定' },
  { id: 'low_risk_automatic', label: '低风险自动', detail: '白名单外仍需批准' },
]
