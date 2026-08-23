'use client'

import { ScheduleListPanel } from '@/components/schedules/schedule-list-panel'
import { PageContainer } from '@/components/shell/page-container'
import { AUTOMATION_TABS, RouteTabs } from '@/components/shell/route-tabs'

export default function SchedulesPage() {
  return (
    <PageContainer
      eyebrow="Automation"
      title="自动化与 Agent"
      description="管理自动化链路的定时触发计划。"
      tabs={<RouteTabs tabs={AUTOMATION_TABS} />}
    >
      <ScheduleListPanel />
    </PageContainer>
  )
}
