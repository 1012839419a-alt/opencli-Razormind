import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react"

import { useFlowStore } from "@/lib/flow/store"
import {
  acceptAgentProposal,
  acceptCollectorNodeProposal,
  previewCollectorNodeProposal,
  rejectCollectorNodeProposal,
  type AgentProposal,
  type CollectorNodeProposal,
  type CollectorProposalDecision,
} from "@/lib/workflow/proposal"
import type { ProposalFocusTarget } from "@/lib/workflow/proposal-focus"

type FitView = (options?: { padding?: number; duration?: number; nodes?: { id: string }[] }) => unknown

const COLLECTOR_PROPOSAL_EVENT = "opencli:collector-proposal"

export function presentCollectorNodeProposal(proposal: CollectorNodeProposal): void {
  window.dispatchEvent(new CustomEvent(COLLECTOR_PROPOSAL_EVENT, { detail: proposal }))
}

export function useWorkflowAgentProposal(options: {
  clearPendingAgentProposal: () => void
  clearProposalFocus: () => void
  fitView: FitView
  focusProposalTargets: (nodeIds: string[], edgeIds: string[]) => void
  importWorkflowProject: (project: ReturnType<typeof acceptAgentProposal>) => void
  pendingAgentProposal: AgentProposal | null | undefined
  setAgentDrawerOpen: Dispatch<SetStateAction<boolean>>
  showToast: (message: string) => void
}) {
  const {
    clearPendingAgentProposal,
    clearProposalFocus,
    fitView,
    focusProposalTargets,
    importWorkflowProject,
    pendingAgentProposal,
    setAgentDrawerOpen,
    showToast,
  } = options
  const [agentProposal, setAgentProposal] = useState<AgentProposal | undefined>(undefined)
  const [collectorProposal, setCollectorProposal] = useState<CollectorNodeProposal | undefined>(undefined)
  const [collectorDecision, setCollectorDecision] = useState<CollectorProposalDecision | undefined>(undefined)

  const acceptProposal = useCallback(
    (proposal: AgentProposal) => {
      try {
        importWorkflowProject(acceptAgentProposal(useFlowStore.getState().workflowProject, proposal))
        showToast("Agent proposal accepted")
        setAgentDrawerOpen(false)
        setAgentProposal(undefined)
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Agent proposal failed")
      }
    },
    [importWorkflowProject, setAgentDrawerOpen, showToast],
  )

  const rejectProposal = useCallback(() => {
    showToast("Agent proposal rejected")
    clearProposalFocus()
    setAgentDrawerOpen(false)
    setAgentProposal(undefined)
  }, [clearProposalFocus, setAgentDrawerOpen, showToast])

  const acceptCollectorProposal = useCallback(
    (proposal: CollectorNodeProposal) => {
      const decision = acceptCollectorNodeProposal(useFlowStore.getState().workflowProject, proposal)
      setCollectorDecision(decision)
      if (decision.status === "conflict") {
        showToast(decision.conflicts[0] ?? "Collector proposal conflicts with newer node edits")
        return
      }
      importWorkflowProject(decision.project)
      showToast(decision.status === "rebased" ? "Collector proposal safely rebased and accepted" : "Collector proposal accepted")
      setAgentDrawerOpen(false)
      setCollectorProposal(undefined)
    },
    [importWorkflowProject, setAgentDrawerOpen, showToast],
  )

  const rejectCollectorProposal = useCallback(
    (proposal: CollectorNodeProposal) => {
      setCollectorDecision(rejectCollectorNodeProposal(useFlowStore.getState().workflowProject, proposal))
      showToast("Collector proposal rejected")
      clearProposalFocus()
      setAgentDrawerOpen(false)
      setCollectorProposal(undefined)
    },
    [clearProposalFocus, setAgentDrawerOpen, showToast],
  )

  const presentAgentProposal = useCallback(
    (proposal: AgentProposal) => {
      setAgentProposal(proposal)
      setAgentDrawerOpen(true)
      showToast("Demand proposal ready")
    },
    [setAgentDrawerOpen, showToast],
  )

  const presentCollectorNodeProposal = useCallback(
    (proposal: CollectorNodeProposal) => {
      const project = useFlowStore.getState().workflowProject
      setCollectorDecision({
        status: "accepted",
        project,
        proposal,
        differences: previewCollectorNodeProposal(project, proposal),
        conflicts: [],
        changed: false,
      })
      setCollectorProposal(proposal)
      setAgentDrawerOpen(true)
      showToast("Collector node proposal ready")
    },
    [setAgentDrawerOpen, showToast],
  )

  useEffect(() => {
    const handleCollectorProposal = (event: Event) => {
      presentCollectorNodeProposal((event as CustomEvent<CollectorNodeProposal>).detail)
    }
    window.addEventListener(COLLECTOR_PROPOSAL_EVENT, handleCollectorProposal)
    return () => window.removeEventListener(COLLECTOR_PROPOSAL_EVENT, handleCollectorProposal)
  }, [presentCollectorNodeProposal])

  useEffect(() => {
    if (!pendingAgentProposal) return
    presentAgentProposal(pendingAgentProposal)
    clearPendingAgentProposal()
  }, [clearPendingAgentProposal, pendingAgentProposal, presentAgentProposal])

  const focusProposalOperation = useCallback(
    (focus: ProposalFocusTarget) => {
      focusProposalTargets(focus.nodeIds, focus.edgeIds)
      if (focus.nodeIds.length > 0) {
        window.setTimeout(() => void fitView({ nodes: focus.nodeIds.map((id) => ({ id })), padding: 0.35, duration: 280 }), 20)
      }
    },
    [fitView, focusProposalTargets],
  )

  return {
    acceptCollectorProposal,
    acceptProposal,
    agentProposal,
    collectorDecision,
    collectorProposal,
    focusProposalOperation,
    presentCollectorNodeProposal,
    rejectCollectorProposal,
    rejectProposal,
  }
}
