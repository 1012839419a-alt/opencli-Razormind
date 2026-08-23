'use client'

import { PageContainer } from '@/components/shell/page-container'
import { CeleryStatsCard } from '@/components/system/celery-stats-card'
import { ChromePoolCard } from '@/components/system/chrome-pool-card'
import { RestartApiCard } from '@/components/system/restart-api-card'
import { SystemConfigCard } from '@/components/system/system-config-card'

export default function SystemPage() {
  return (
    <PageContainer
      title="系统与运维"
      description="部署配置与计算池的运行状态一览；重启操作会影响全部用户，请谨慎执行。"
    >
      <SystemConfigCard />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChromePoolCard />
        <CeleryStatsCard />
      </div>
      <RestartApiCard />
    </PageContainer>
  )
}
