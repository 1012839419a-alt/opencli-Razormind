'use client'

import { usePlanHealth } from '@/lib/api/hooks'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'

/**
 * Aggregate health signal for one Plan, derived client-side from its most
 * recent Plan Health rows (GET /plans/{id}/health, issue 04). There is no
 * server-computed "plan health" field on PlanRead — health is a separate,
 * paginated, node-level record stream — so this rolls the last few rows
 * (newest first, across every run_key) into a single badge for the list.
 */
export function PlanHealthBadge({ planId }: { planId: string }) {
  const { data, isLoading, isError } = usePlanHealth(planId, { limit: 5 })
  const rows = data?.data ?? []

  if (isLoading) {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        …
      </Badge>
    )
  }
  if (isError || rows.length === 0) {
    return <StatusBadge status="unknown" />
  }

  const successCount = rows.filter((row) => row.success).length
  const status = successCount === rows.length ? 'healthy' : successCount === 0 ? 'failed' : 'degraded'
  const title = `最近 ${rows.length} 条节点运行记录：${successCount} 成功 / ${rows.length - successCount} 失败`

  return (
    <span title={title}>
      <StatusBadge status={status} />
    </span>
  )
}
