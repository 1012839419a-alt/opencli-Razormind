'use client'

import { BrainCircuit, Braces, ChartNoAxesCombined, Database, LayoutDashboard, Network, Orbit, Settings2, Workflow } from 'lucide-react'
import Link from 'next/link'

import { cn } from '@/lib/utils'

export type ProjectNavigationSection =
  | 'overview'
  | 'orchestration'
  | 'data'
  | 'evidence'
  | 'relationships'
  | 'galaxy'
  | 'apiAccess'
  | 'operations'

const PROJECT_SECTIONS = [
  { id: 'overview', label: '概览', icon: LayoutDashboard },
  { id: 'orchestration', label: '业务编排', icon: Workflow },
  { id: 'data', label: '数据工作台', icon: Database },
  { id: 'evidence', label: '逻辑与证据', icon: BrainCircuit },
  { id: 'relationships', label: '证据关系', icon: Network },
  { id: 'galaxy', label: 'Galaxy', icon: Orbit },
  { id: 'apiAccess', label: 'API / MCP', icon: Braces },
  { id: 'operations', label: '日志监测', icon: ChartNoAxesCombined },
  { id: 'settings', label: '设置', icon: Settings2 },
] as const

export function ProjectNavigation({
  active,
  workspaceId,
  projectId,
  workflowId,
}: {
  active: ProjectNavigationSection
  workspaceId: string | null
  projectId: string | null
  workflowId?: string | null
}) {
  const overviewHref = workspaceId && projectId
    ? `/studio/projects/${projectId}?workspace=${workspaceId}`
    : null
  const orchestrationHref = workspaceId && projectId
    ? `/studio/workflow?workspace=${workspaceId}&project=${projectId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const dataHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/data?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const evidenceHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/evidence?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const relationshipsHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/relationships?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const galaxyHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/galaxy?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const apiAccessHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/api?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const operationsHref = workspaceId && projectId
    ? `/studio/projects/${projectId}/operations?workspace=${workspaceId}${workflowId ? `&workflow=${workflowId}` : ''}`
    : null
  const sectionHrefs = {
    overview: overviewHref,
    orchestration: orchestrationHref,
    data: dataHref,
    evidence: evidenceHref,
    relationships: relationshipsHref,
    galaxy: galaxyHref,
    apiAccess: apiAccessHref,
    operations: operationsHref,
    settings: null,
  } satisfies Record<(typeof PROJECT_SECTIONS)[number]['id'], string | null>

  return (
    <nav className="-mx-1 flex min-w-0 items-center gap-1 overflow-x-auto px-1" aria-label="项目导航">
      {PROJECT_SECTIONS.map((section) => {
        const href = sectionHrefs[section.id]
        const isActive = section.id === active
        const Icon = section.icon
        const className = cn(
          'inline-flex h-11 shrink-0 items-center rounded-xs px-3 text-xs transition-colors',
          isActive ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground',
          href && !isActive && 'hover:bg-muted/60 hover:text-foreground',
          !href && 'cursor-not-allowed opacity-45',
        )

        return href ? (
          <Link key={section.id} href={href} aria-current={isActive ? 'page' : undefined} className={className}>
            <Icon className="mr-1.5 size-3.5" aria-hidden />{section.label}
          </Link>
        ) : (
          <span key={section.id} className={className} aria-disabled="true" title="项目范围能力将在后续生命周期接线中开放">
            <Icon className="mr-1.5 size-3.5" aria-hidden />{section.label}
          </span>
        )
      })}
    </nav>
  )
}
