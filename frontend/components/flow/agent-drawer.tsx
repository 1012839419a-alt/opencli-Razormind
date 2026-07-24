"use client"

import { AlertTriangle, Check, CheckCircle2, CircleDot, GitCompareArrows, X, XCircle } from "lucide-react"
import duplicatePushFixture from "@/lib/workflow/fixtures/agent-proposal-duplicate-push.json"
import {
  parseAgentProposal,
  type AgentProposal,
  type CollectorNodeProposal,
  type CollectorProposalDecision,
} from "@/lib/workflow/proposal"
import { summarizeAgentProposal, type ProposalRiskTone } from "@/lib/workflow/proposal-summary"
import { getProposalOperationFocus, type ProposalFocusTarget } from "@/lib/workflow/proposal-focus"
import { cn } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

const fixtureProposal = parseAgentProposal(duplicatePushFixture)

export type AgentDrawerProps = {
  open?: boolean
  proposal?: AgentProposal
  collectorProposal?: CollectorNodeProposal
  collectorDecision?: CollectorProposalDecision
  onAccept?: (proposal: AgentProposal) => void
  onReject?: (proposal: AgentProposal) => void
  onAcceptCollector?: (proposal: CollectorNodeProposal) => void
  onRejectCollector?: (proposal: CollectorNodeProposal) => void
  onFocusOperation?: (focus: ProposalFocusTarget) => void
  onClose?: () => void
  acceptDisabled?: boolean
  rejectDisabled?: boolean
  className?: string
}

export function AgentDrawer({
  open = true,
  proposal = fixtureProposal,
  collectorProposal,
  collectorDecision,
  onAccept,
  onReject,
  onAcceptCollector,
  onRejectCollector,
  onFocusOperation,
  onClose,
  acceptDisabled = false,
  rejectDisabled = false,
  className,
}: AgentDrawerProps) {
  if (!open) return null
  if (collectorProposal) {
    return (
      <CollectorProposalDrawer
        proposal={collectorProposal}
        decision={collectorDecision}
        onAccept={onAcceptCollector}
        onReject={onRejectCollector}
        onClose={onClose}
        acceptDisabled={acceptDisabled}
        rejectDisabled={rejectDisabled}
        className={className}
      />
    )
  }

  const summary = summarizeAgentProposal(proposal)
  const riskClasses = riskToneClasses(summary.riskTone)

  return (
    <aside
      className={cn(
        "fixed inset-x-3 bottom-3 z-40 mx-auto max-w-6xl overflow-hidden rounded-lg border border-border bg-background/95 shadow-2xl backdrop-blur",
        className,
      )}
      aria-label="Agent proposal drawer"
    >
      <div className="flex flex-col gap-3 p-3 md:p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className={cn("capitalize", riskClasses.badge)}>
                <AlertTriangle className="size-3" />
                {summary.risk} risk
              </Badge>
              <Badge variant={summary.failedEvidence > 0 ? "destructive" : "secondary"}>
                {summary.evidencePassed}/{summary.evidenceTotal} checks passed
              </Badge>
              <Badge variant="secondary">{summary.operationCount} ops</Badge>
            </div>
            <h2 className="truncate text-sm font-semibold text-foreground md:text-base">
              {summary.title}
            </h2>
            <p className="line-clamp-2 max-w-3xl text-xs leading-5 text-muted-foreground md:text-sm">
              {summary.summary}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onReject?.(proposal)}
              disabled={rejectDisabled}
            >
              <XCircle />
              Reject
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => onAccept?.(proposal)}
              disabled={acceptDisabled}
            >
              <CheckCircle2 />
              Accept
            </Button>
            {onClose ? (
              <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close drawer">
                <X />
              </Button>
            ) : null}
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(280px,0.7fr)]">
          <section className="rounded-md border border-border bg-muted/20">
            <div className="border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Operations
            </div>
            <ScrollArea className="h-36">
              <div className="divide-y divide-border">
                {summary.operationSummaries.map((operation) => (
                  <button
                    key={operation.id}
                    type="button"
                    className="grid w-full grid-cols-[104px_minmax(0,1fr)] gap-2 px-3 py-2 text-left transition-colors hover:bg-accent"
                    onClick={() => onFocusOperation?.(getProposalOperationFocus(proposal.operations[operation.index]))}
                  >
                    <span className="text-xs font-medium text-foreground">{operation.label}</span>
                    <span className="truncate text-xs text-muted-foreground">{operation.detail}</span>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </section>

          <section className="rounded-md border border-border bg-muted/20">
            <div className="border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Validation Evidence
            </div>
            <ScrollArea className="h-36">
              <div className="divide-y divide-border">
                {proposal.validationEvidence.map((item) => (
                  <div key={item.id} className="grid grid-cols-[18px_minmax(0,1fr)] gap-2 px-3 py-2">
                    {item.passed ? (
                      <Check className="mt-0.5 size-3.5 text-emerald-600" />
                    ) : (
                      <CircleDot className="mt-0.5 size-3.5 text-amber-600" />
                    )}
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-foreground">{item.label}</div>
                      {item.details ? (
                        <div className="line-clamp-2 text-xs leading-5 text-muted-foreground">{item.details}</div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </section>
        </div>
      </div>
    </aside>
  )
}

function CollectorProposalDrawer({
  proposal,
  decision,
  onAccept,
  onReject,
  onClose,
  acceptDisabled,
  rejectDisabled,
  className,
}: {
  proposal: CollectorNodeProposal
  decision?: CollectorProposalDecision
  onAccept?: (proposal: CollectorNodeProposal) => void
  onReject?: (proposal: CollectorNodeProposal) => void
  onClose?: () => void
  acceptDisabled: boolean
  rejectDisabled: boolean
  className?: string
}) {
  const differences = decision?.differences
  const conflicted = decision?.status === "conflict"
  return (
    <aside
      className={cn(
        "fixed inset-x-3 bottom-3 z-40 mx-auto max-w-6xl overflow-hidden rounded-lg border border-border bg-background/95 shadow-2xl backdrop-blur",
        className,
      )}
      aria-label="Collector node proposal drawer"
    >
      <div className="flex flex-col gap-3 p-3 md:p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">
                <GitCompareArrows className="size-3" />
                Node patch
              </Badge>
              <Badge variant="outline">{proposal.operations.length} ops</Badge>
              <Badge variant={conflicted ? "destructive" : "outline"}>
                {conflicted ? "CAS conflict" : `base ${proposal.baseRevision}`}
              </Badge>
            </div>
            <h2 className="truncate text-sm font-semibold text-foreground md:text-base">
              {proposal.summary}
            </h2>
            <p className="text-xs text-muted-foreground">
              Target node: <span className="font-mono">{proposal.nodeId}</span>. Agent changes are applied only through the structured collector whitelist.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => onReject?.(proposal)} disabled={rejectDisabled}>
              <XCircle />
              Reject
            </Button>
            <Button type="button" size="sm" onClick={() => onAccept?.(proposal)} disabled={acceptDisabled || conflicted}>
              <CheckCircle2 />
              Accept
            </Button>
            {onClose ? (
              <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close drawer">
                <X />
              </Button>
            ) : null}
          </div>
        </div>

        {conflicted ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {decision.conflicts.join("; ")}
          </div>
        ) : null}

        <section className="rounded-md border border-border bg-muted/20">
          <div className="border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Node differences
          </div>
          <ScrollArea className="h-40">
            <div className="divide-y divide-border">
              {proposal.operations.map((operation, index) => {
                const difference = differences?.[index]
                return (
                  <div key={`${proposal.proposalId}-${index}`} className="grid gap-1 px-3 py-2">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium text-foreground">{collectorOperationLabel(operation.type)}</span>
                      <Badge variant={difference?.status === "conflict" ? "destructive" : "outline"}>
                        {difference?.status ?? "pending"}
                      </Badge>
                    </div>
                    <div className="truncate font-mono text-[11px] text-muted-foreground">
                      {difference?.path ?? collectorOperationPath(proposal.nodeId, operation)}
                    </div>
                    {difference?.message ? (
                      <div className="text-xs text-destructive">{difference.message}</div>
                    ) : null}
                    {difference ? (
                      <div className="grid gap-1 md:grid-cols-2">
                        <pre className="max-h-24 overflow-auto rounded bg-background px-2 py-1 text-[10px] text-muted-foreground">
                          {`before: ${formatCollectorDiffValue(difference.before)}`}
                        </pre>
                        <pre className="max-h-24 overflow-auto rounded bg-background px-2 py-1 text-[10px] text-foreground">
                          {`after: ${formatCollectorDiffValue(difference.after)}`}
                        </pre>
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </ScrollArea>
        </section>
      </div>
    </aside>
  )
}

function formatCollectorDiffValue(value: unknown): string {
  if (value === undefined) return "<missing>"
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function collectorOperationLabel(type: CollectorNodeProposal["operations"][number]["type"]): string {
  return {
    addSource: "Add source",
    updateSource: "Update source",
    removeSource: "Remove source",
    moveSource: "Reorder source",
    setExecution: "Update execution",
  }[type]
}

function collectorOperationPath(
  nodeId: string,
  operation: CollectorNodeProposal["operations"][number],
): string {
  if (operation.type === "setExecution") return `/nodes/${nodeId}/params/execution/${operation.field}`
  if (operation.type === "moveSource") return `/nodes/${nodeId}/params/sources`
  const sourceId = operation.type === "addSource" ? operation.source.sourceId : operation.sourceId
  return `/nodes/${nodeId}/params/sources/${String(sourceId)}`
}

function riskToneClasses(tone: ProposalRiskTone) {
  if (tone === "danger") {
    return { badge: "border-destructive/30 bg-destructive/10 text-destructive" }
  }
  if (tone === "warning") {
    return { badge: "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300" }
  }
  return { badge: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300" }
}
