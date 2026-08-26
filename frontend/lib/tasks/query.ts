const TASK_STATUSES = new Set(['running', 'completed', 'failed', 'pending'])

export function normalizeTaskStatus(value: string | null): string {
  return value && TASK_STATUSES.has(value) ? value : ''
}

export function normalizeTaskPage(value: string | null): number {
  const page = Number(value)
  return Number.isInteger(page) && page > 0 ? page : 1
}

export function queryForTaskStatus(currentQuery: string, nextStatus: string): string {
  const params = new URLSearchParams(currentQuery)
  const status = normalizeTaskStatus(nextStatus)
  if (status) params.set('status', status)
  else params.delete('status')
  params.delete('page')
  return params.toString()
}

export function queryForTaskPage(currentQuery: string, nextPage: number): string {
  const params = new URLSearchParams(currentQuery)
  const page = Number.isInteger(nextPage) && nextPage > 1 ? nextPage : 1
  if (page > 1) params.set('page', String(page))
  else params.delete('page')
  return params.toString()
}

export function pathWithQuery(pathname: string, query: string): string {
  return query ? `${pathname}?${query}` : pathname
}
