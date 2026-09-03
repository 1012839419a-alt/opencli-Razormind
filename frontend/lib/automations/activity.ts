import type { OperationsAgentRun } from '@/lib/api/types'

export function latestOperationsAgentRuns(runs: OperationsAgentRun[]) {
  return new Map(runs.map((run) => [run.operations_agent_id, run]))
}
