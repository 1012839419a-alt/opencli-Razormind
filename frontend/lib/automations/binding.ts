import type { OperationsAgent, OperationsAgentMode } from '@/lib/api/types'

export function runnableOperationsAgents(agents: OperationsAgent[]) {
  return agents.filter(
    (agent) =>
      !agent.disabled
      && agent.current_published_version !== null
      && agent.current_profile.mode !== 'low_risk_automatic',
  )
}

export function compatibleOperationsAgents(
  agents: OperationsAgent[],
  mode: OperationsAgentMode,
) {
  return runnableOperationsAgents(agents).filter(
    (agent) => agent.current_profile.mode === mode,
  )
}
