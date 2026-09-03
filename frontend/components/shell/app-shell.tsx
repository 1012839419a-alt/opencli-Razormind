'use client'

import { Suspense, useEffect, useState } from 'react'

import { AppRouteTransition } from '@/components/motion/app-route-transition'
import { AppHeader } from '@/components/shell/app-header'
import { AppSidebar } from '@/components/shell/app-sidebar'
import { CommandPalette } from '@/components/shell/command-palette'
import { GlobalAgentDock } from '@/components/shell/global-agent-dock'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { useAuth } from '@/components/auth/auth-provider'

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const [commandOpen, setCommandOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)
  useEffect(() => {
    if (status !== 'authenticated') {
      setCommandOpen(false)
      setAgentOpen(false)
    }
  }, [status])
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader
          onOpenAgent={() => setAgentOpen(true)}
          onOpenCommand={() => setCommandOpen(true)}
        />
        <div className="relative z-0 flex-1 overflow-auto overflow-x-clip bg-background [scrollbar-gutter:stable]">
          <AppRouteTransition>{children}</AppRouteTransition>
        </div>
      </SidebarInset>
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      <Suspense fallback={null}>
        <GlobalAgentDock open={agentOpen} onOpenChange={setAgentOpen} />
      </Suspense>
    </SidebarProvider>
  )
}
