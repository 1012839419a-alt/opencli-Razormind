import { Cloud, Code2, Sparkles, Terminal } from 'lucide-react'

export const AUTOMATION_EXECUTORS = [
  { id: 'codex', name: 'Codex', icon: Code2, color: 'text-sky-400' },
  { id: 'claude', name: 'Claude', icon: Sparkles, color: 'text-orange-400' },
  { id: 'chatcloud', name: 'ChatCloud', icon: Cloud, color: 'text-violet-400' },
  { id: 'custom', name: '自定义', icon: Terminal, color: 'text-emerald-400' },
] as const

export function automationExecutorMeta(id: string) {
  return AUTOMATION_EXECUTORS.find((item) => item.id === id) ?? AUTOMATION_EXECUTORS[3]
}
