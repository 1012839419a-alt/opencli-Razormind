import { expect, test } from '@playwright/test'

test.use({ baseURL: 'http://127.0.0.1:3001' })

const workspace = { id: 'workspace-1', name: 'Research', slug: 'research', active: true, created_at: '', updated_at: '' }
const instance = { id: 'instance-1', label: 'Chromium slot A', granted_capabilities: ['snapshot'] }

async function mockBrowserSpaces(page, options = {}) {
  const state = {
    spaces: options.spaces ?? [],
    events: options.events ?? [],
    createError: options.createError,
    submitError: options.submitError,
  }
  await page.addInitScript(() => sessionStorage.setItem('opencli.bootstrapIdentityToken', 'test-identity'))
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const json = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ data }) })
    if (url.pathname === '/api/v1/auth/me') return json({ subject: 'test-agent', email: null, name: 'Test Agent', username: null, picture: null, is_platform_admin: true, auth_method: 'development' })
    if (url.pathname === '/api/v1/workspaces') return json([workspace])
    if (url.pathname.endsWith('/browser-spaces') && request.method() === 'GET') return json({ spaces: state.spaces, available_instances: [instance] })
    if (url.pathname.endsWith('/browser-spaces') && request.method() === 'POST') {
      if (state.createError) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: state.createError }) })
      state.spaces = [{ id: 'space-1', workspace_id: workspace.id, browser_instance_id: instance.id, owner_type: 'operator', owner_id: 'agent-7', status: 'idle', granted_capabilities: ['snapshot'] }]
      return json(state.spaces[0], 201)
    }
    if (url.pathname.endsWith('/space-1/tasks')) {
      if (state.submitError) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: state.submitError }) })
      state.spaces[0].latest_task = { id: 'task-1', operation_id: 'op-1', capability: 'snapshot', status: 'completed', result: { title: 'safe page', cookies: 'must-not-render' } }
      state.events = [{ id: 'event-1', sequence: 1, kind: 'completed', payload: { title: 'safe page', authorization: 'must-not-render' }, created_at: '2026-01-01T00:00:00Z' }]
      return json({ task_id: 'task-1', operation_id: 'op-1', status: 'completed', result: state.spaces[0].latest_task.result })
    }
    if (url.pathname.endsWith('/space-1/cancel')) {
      state.spaces[0].latest_task = { id: 'task-1', operation_id: 'op-1', capability: 'snapshot', status: 'cancelled' }
      return json({ task_id: 'task-1', operation_id: 'op-1', status: 'cancelled' })
    }
    if (url.pathname.endsWith('/space-1/close')) {
      state.spaces[0].status = 'closed'
      return json(state.spaces[0])
    }
    if (url.pathname.endsWith('/space-1/events')) return json(state.events)
    return route.fallback()
  })
}

test('creates a space only from an allowed existing browser instance', async ({ page }) => {
  await mockBrowserSpaces(page)
  await page.goto('/browsers')
  await page.getByLabel('已有 BrowserInstance').selectOption('instance-1')
  await page.getByLabel('Owner ID').fill('agent-7')
  await page.getByRole('button', { name: '创建独占 Space' }).click()
  await expect(page.getByText('Space 已创建并独占该浏览器实例。')).toBeVisible()
  await expect(page.getByText('agent-7').first()).toBeVisible()
})

test('submits a granted capability and redacts sensitive result fields', async ({ page }) => {
  await mockBrowserSpaces(page, { spaces: [{ id: 'space-1', workspace_id: workspace.id, browser_instance_id: instance.id, owner_type: 'operator', owner_id: 'agent-7', status: 'idle', granted_capabilities: ['snapshot'] }] })
  await page.goto('/browsers')
  await page.getByRole('button', { name: '提交任务' }).click()
  await expect(page.getByText('safe page').first()).toBeVisible()
  await expect(page.getByText('[redacted]')).toHaveCount(2)
  await expect(page.getByText('must-not-render')).toHaveCount(0)
})

test('shows the instance ownership typed error without a fallback', async ({ page }) => {
  await mockBrowserSpaces(page, { createError: 'browser_instance_in_use' })
  await page.goto('/browsers')
  await page.getByLabel('已有 BrowserInstance').selectOption('instance-1')
  await page.getByLabel('Owner ID').fill('agent-7')
  await page.getByRole('button', { name: '创建独占 Space' }).click()
  await expect(page.getByText(/browser_instance_in_use：该浏览器实例已由另一个 Space 保留/)).toBeVisible()
  await expect(page.getByText(/共享标签/)).toHaveCount(0)
})

test('confirms cancellation and close before sending lifecycle actions', async ({ page }) => {
  await mockBrowserSpaces(page, { spaces: [{ id: 'space-1', workspace_id: workspace.id, browser_instance_id: instance.id, owner_type: 'operator', owner_id: 'agent-7', status: 'running', granted_capabilities: ['snapshot'], latest_task: { id: 'task-1', operation_id: 'op-1', capability: 'snapshot', status: 'running' } }] })
  await page.goto('/browsers')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '取消任务' }).click()
  await expect(page.getByText('已请求取消任务。')).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '关闭 Space' }).click()
  await expect(page.getByText('Space 已关闭。')).toBeVisible()
})
