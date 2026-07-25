'use client'

import { use } from 'react'

import { ProjectGraphExplorer } from '@/components/records/project-graph-explorer'

export default function ProjectGalaxyPage({
  params,
}: {
  params: Promise<{ projectId: string }>
}) {
  const { projectId } = use(params)
  return <ProjectGraphExplorer projectId={projectId} mode="galaxy" />
}
