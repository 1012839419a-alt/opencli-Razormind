'use client'

import { useState } from 'react'

import { AppRouteTransition } from '@/components/motion/app-route-transition'
import { AppHeader } from '@/components/shell/app-header'
import { AppSidebar } from '@/components/shell/app-sidebar'
import { CommandPalette } from '@/components/shell/command-palette'
import { GlobalAgentDock } from '@/components/shell/global-agent-dock'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)

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
      <GlobalAgentDock open={agentOpen} onOpenChange={setAgentOpen} />
    </SidebarProvider>
  )
}
