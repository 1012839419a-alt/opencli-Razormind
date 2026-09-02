'use client'

import { Bot } from 'lucide-react'

import { Button } from '@/components/ui/button'

export function GlobalAgentBubble({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      size="icon"
      className="fixed bottom-4 right-4 z-40 size-12 rounded-full shadow-lg"
      aria-label="打开全局 Agent"
      onClick={onClick}
    >
      <Bot className="size-5" aria-hidden />
      <span className="sr-only">打开全局 Agent</span>
    </Button>
  )
}
