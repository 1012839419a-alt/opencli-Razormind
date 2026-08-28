import { expect, test } from '@playwright/test'

const api = (path) => `**/api/v1${path}`

const workspace = {
  id: 'workspace-gpu',
  name: 'GPU fixture workspace',
  slug: 'gpu-fixture-workspace',
  active: true,
  created_at: '2026-08-28T00:00:00Z',
  updated_at: '2026-08-28T00:00:00Z',
}

const project = {
  id: 'project-gpu',
  workspace_id: workspace.id,
  name: 'GPU fixture project',
  slug: 'gpu-fixture-project',
  description: null,
  app_type: 'workflow',
  primary_workflow_id: 'workflow-gpu',
  created_by_user_id: 'e2e-admin',
  archived: false,
  created_at: '2026-08-28T00:00:00Z',
  updated_at: '2026-08-28T00:00:00Z',
}

const workflow = {
  id: 'workflow-gpu',
  project_id: project.id,
  name: 'GPU fixture workflow',
  description: null,
  current_published_version: 1,
  archived: false,
  created_at: '2026-08-28T00:00:00Z',
  updated_at: '2026-08-28T00:00:00Z',
}

const graphPreview = {
  workspace_id: workspace.id,
  project_id: project.id,
  project_name: project.name,
  strategy: 'server-aggregated-sample',
  truncated: false,
  max_nodes: 700,
  nodes: [
    {
      id: 'project-node',
      kind: 'project',
      label: project.name,
      subtitle: 'Fixture project root',
      count: 1,
      record_id: null,
      source_id: null,
      workflow_id: null,
      workflow_run_id: null,
      url: null,
      preview: null,
      status: 'ready',
      source_published_at: null,
      created_at: '2026-08-28T00:00:00Z',
    },
    {
      id: 'source-node',
      kind: 'source',
      label: 'Fixture source',
      subtitle: 'Fixture source detail',
      count: 4,
      record_id: null,
      source_id: 'source-gpu',
      workflow_id: null,
      workflow_run_id: null,
      url: 'https://example.test/source',
      preview: null,
      status: 'ready',
      source_published_at: '2026-08-28T00:00:00Z',
      created_at: '2026-08-28T00:00:00Z',
    },
  ],
  edges: [
    {
      id: 'project-source',
      source: 'project-node',
      target: 'source-node',
      kind: 'contains',
      label: 'contains',
      weight: 1,
      bidirectional: true,
    },
  ],
  stats: {
    total_records: 4,
    sampled_records: 4,
    hidden_records: 0,
    total_sources: 1,
    total_workflows: 1,
    total_runs: 0,
    visible_nodes: 2,
    visible_edges: 1,
  },
  generated_at: '2026-08-28T00:00:00Z',
}

async function disableWebGl2(page) {
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function getContextWithoutWebGl2(
      contextId,
      ...argumentsAfterContextId
    ) {
      if (contextId === 'webgl2') return null
      return getContext.call(this, contextId, ...argumentsAfterContextId)
    }
  })
}

async function installGraphFixtures(page) {
  await page.route(api('/auth/login'), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      success: true,
      data: {
        access_token: 'e2e-token',
        token_type: 'bearer',
        using_default_password: false,
      },
    }),
  }))
  await page.route(api('/auth/me'), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      success: true,
      data: {
        subject: 'e2e-admin',
        name: 'E2E Admin',
        is_platform_admin: true,
        auth_method: 'password',
      },
    }),
  }))
  await page.route(api('/workspaces'), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [workspace] }),
  }))
  await page.route(api(`/workspaces/${workspace.id}/projects`), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [project] }),
  }))
  await page.route(api(`/workspaces/${workspace.id}/projects/${project.id}/workflows`), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [workflow] }),
  }))
  await page.route(`**/api/v1/workspaces/${workspace.id}/projects/${project.id}/record-graph**`, (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: graphPreview }),
  }))
}

async function goAuthed(page, path) {
  await page.goto(`/login?returnTo=${encodeURIComponent(path)}`)
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('admin')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(new RegExp(`${path.split('?')[0].replaceAll('/', '\\/')}(?:\\?.*)?$`))
}

test('records graph keeps fallback nodes selectable without WebGL2', async ({ page }) => {
  await disableWebGl2(page)
  await installGraphFixtures(page)
  await goAuthed(page, '/records/graph')

  await expect(page.locator('[data-gpu-surface="record-relationship-graph"]'))
    .toHaveAttribute('data-gpu-backend', 'fallback')
  await page.locator('[data-record-graph-fallback]').getByRole('button', { name: /Fixture source/ }).click()
  await expect(page.getByRole('heading', { name: 'Fixture source', exact: true })).toBeVisible()
})

test('Galaxy fallback nodes open the existing inspector without WebGL2', async ({ page }) => {
  await disableWebGl2(page)
  await installGraphFixtures(page)
  await goAuthed(page, `/studio/projects/${project.id}/galaxy?workspace=${workspace.id}`)

  await expect(page.locator('[data-gpu-surface="project-galaxy-graph"]'))
    .toHaveAttribute('data-gpu-backend', 'fallback')
  await page.locator('[data-project-graph-fallback]').getByRole('button', { name: /Fixture source/ }).click()
  await expect(page.getByRole('heading', { name: 'Fixture source', exact: true })).toBeVisible()
})
