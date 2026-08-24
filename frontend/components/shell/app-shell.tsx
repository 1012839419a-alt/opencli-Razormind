'use client'

import { useEffect, useState } from 'react'

import { AppRouteTransition } from '@/components/motion/app-route-transition'
import { AppHeader } from '@/components/shell/app-header'
import { AppSidebar } from '@/components/shell/app-sidebar'
import { CommandPalette } from '@/components/shell/command-palette'
import { GlobalAgentBubble } from '@/components/shell/global-agent-bubble'
import { GlobalAgentDock } from '@/components/shell/global-agent-dock'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

export function AppShell({ children }: { children: React.ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)
  const [agentPrompt, setAgentPrompt] = useState('')

  useEffect(() => {
    function openAgent(event: Event) {
      const prompt = (event as CustomEvent<{ prompt?: string }>).detail?.prompt?.trim() ?? ''
      setAgentPrompt(prompt)
      setAgentOpen(true)
    }
    window.addEventListener('open-global-agent', openAgent)
    return () => window.removeEventListener('open-global-agent', openAgent)
  }, [])
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <AppHeader
          onOpenCommand={() => setCommandOpen(true)}
        />
        <div className="relative z-0 flex-1 overflow-auto overflow-x-clip bg-background [scrollbar-gutter:stable]">
          <AppRouteTransition>{children}</AppRouteTransition>
        </div>
      </SidebarInset>
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
      <GlobalAgentBubble onClick={() => { setAgentPrompt(''); setAgentOpen(true) }} />
      <GlobalAgentDock open={agentOpen} onOpenChange={setAgentOpen} initialPrompt={agentPrompt} />
    </SidebarProvider>
  )
}
