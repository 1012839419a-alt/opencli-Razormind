import type { ReactNode } from 'react'

import { PageContainer } from '@/components/shell/page-container'
import { CONTROL_TABS, RouteTabs } from '@/components/shell/route-tabs'

export default function ControlLayout({ children }: { children: ReactNode }) {
  return (
    <PageContainer
      eyebrow="CONTROL PLANE"
      title="控制与安全"
      description="控制回路的证据台账、全局熔断开关、自动化门禁报告与 ODP 数据面健康状况。"
      tabs={<RouteTabs tabs={CONTROL_TABS} />}
    >
      {children}
    </PageContainer>
  )
}
