'use client'

import { PlanListPanel } from '@/components/plans/plan-list-panel'
import { PageContainer } from '@/components/shell/page-container'
import { AUTOMATION_TABS, RouteTabs } from '@/components/shell/route-tabs'

export default function PlansPage() {
  return (
    <PageContainer
      eyebrow="Automation"
      title="自动化与 Agent"
      description="管理 Collection Canvas 计划图：创建、重命名、手动运行与健康状况。"
      tabs={<RouteTabs tabs={AUTOMATION_TABS} />}
    >
      <PlanListPanel />
    </PageContainer>
  )
}
