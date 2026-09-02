import { redirect } from 'next/navigation'

type TemplateRouteProps = {
  searchParams: Promise<{ workspace?: string }>
}

export default async function StudioTemplatesPage({ searchParams }: TemplateRouteProps) {
  const { workspace } = await searchParams
  const params = new URLSearchParams({ type: 'template' })
  if (workspace) params.set('workspace', workspace)
  redirect(`/plugins?${params.toString()}`)
}
