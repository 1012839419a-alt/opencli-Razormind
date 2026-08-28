export async function installActionCenterFixtures(page) {
  const taskRequests = []
  const controlRequests = []
  const paginated = (data) => ({
    success: true,
    data,
    meta: { total: data.length, page: 1, pages: 1, limit: 100 },
  })
  const controlActions = Array.from({ length: 24 }, (_, index) => ({
    id: `control-e2e-${index}`,
    source_id: `source-e2e-${index}`,
    action_type: 'pause_collection',
    reason: `E2E evidence ${index}`,
    state: 'pending',
    mode: 'advisory',
    executed: false,
    outcome: null,
    created_at: '2026-08-29T00:00:00Z',
  }))

  await page.route('**/api/v1/tasks*', (route) => {
    const status = new URL(route.request().url()).searchParams.get('status')
    taskRequests.push(status)
    const tasks =
      status === 'failed'
        ? [
            {
              id: 'task-failed-e2e',
              source_id: 'source-e2e',
              source_name: 'Failed source',
              trigger_type: 'manual',
              priority: 1,
              status: 'failed',
              created_at: '2026-08-29T00:00:00Z',
              updated_at: '2026-08-29T00:00:00Z',
            },
          ]
        : []
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(paginated(tasks)) })
  })
  await page.route('**/api/v1/notifications/logs*', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(paginated([])) }),
  )
  await page.route('**/api/v1/notifications/rules', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }) }),
  )
  await page.route('**/api/v1/governance/workspaces', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }) }),
  )
  await page.route('**/api/v1/control/actions*', (route) => {
    const query = new URL(route.request().url()).searchParams
    controlRequests.push({
      source_id: query.get('source_id'),
      mode: query.get('mode'),
      outcome: query.get('outcome'),
      page: query.get('page'),
      limit: query.get('limit'),
    })
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(paginated(controlActions)),
    })
  })

  return { controlRequests, taskRequests }
}
