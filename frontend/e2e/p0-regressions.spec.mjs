import { expect, test } from '@playwright/test'
import { installActionCenterFixtures } from './action-center-fixtures.mjs'

const api = (path) => `**/api/v1${path}`

async function installPluginFixtures(page) {
  await page.route(api('/plugins'), (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [
      { id: 'e2e-provider', providerKey: 'e2e/test-plugin', name: 'E2E Provider', author: 'E2E', version: '1.0.0', sourceKind: 'bundled', sourceDigest: 'e2e', manifestSpecVersion: '1.0', signatureState: 'bundled', labels: { zh_Hans: 'E2E Provider' }, descriptions: { zh_Hans: 'Deterministic test provider' }, icon: 'globe', pluginTypes: ['adapter'], runtimeStatus: 'READY', capabilities: [{ id: 'browser', family: 'tool', key: 'browser', label: 'Browser', blockers: [], flowCapability: true, status: 'READY' }], nodeDefinitions: [], manifest: {}, permissions: {}, blockers: [], bundled: false, installedAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' },
    ] }),
  }))
  await page.route('**/api/workflow/capabilities', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { version: 'test', catalog: [], primitives: [], channels: [], notifiers: [], triggers: [], resources: [] } }),
  }))
  await page.route('**/api/v1/plugins/capabilities', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: { version: 'opencli.node-capabilities.v1', authority: 'backend', nodes: [{
      id: 'e2e-provider.browser', label: 'Browser', description: 'E2E browser capability', category: 'tool', origin: 'plugin', provider: 'e2e/test-plugin', source: 'backend.workflow.node_capabilities', readiness: 'runnable', runtimeBinding: 'workflow.external-tool.capability', kind: 'action', capability: 'tool', icon: 'Globe2', inputPorts: [], outputPorts: [], parameters: [], difyNodeTypes: [], missing: [],
    }], categories: [{ id: 'tool', label: 'Tool', count: 1 }], summary: { total: 1, byReadiness: { runnable: 1 }, byOrigin: { plugin: 1 } } } }),
  }))
  await page.route('**/api/v1/workspaces', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [{ id: 'e2e-workspace', name: 'E2E Workspace' }] }) }))
  await page.route('**/api/v1/workspaces/*/projects', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [], meta: { total: 0, page: 1, pages: 0, limit: 20 } }) }))
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.addInitScript(() => {
    const style = document.createElement('style')
    style.textContent = '*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }'
    document.documentElement.appendChild(style)
  })
  await page.route('**/api/v1/auth/login', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { access_token: 'e2e-token', token_type: 'bearer', using_default_password: false } }) }))
  await page.route('**/api/v1/auth/me', (route) => {
    if (route.request().headers().authorization !== 'Bearer e2e-token') throw new Error('auth/me missing Bearer e2e-token')
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { subject: 'e2e-admin', name: 'E2E Admin', is_platform_admin: true, auth_method: 'password' } }) })
  })
})
async function goAuthed(page, path) {
  await page.goto(`/login?returnTo=${encodeURIComponent(path)}`)
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('admin')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(new RegExp(`${path.split('?')[0].replaceAll('/', '\\/')}(?:\\?.*)?$`), { timeout: 10000 })
}

test('plugins tabs expose semantic selection and installed capability detail', async ({ page }) => {
  await installPluginFixtures(page)
  await goAuthed(page, '/plugins')
  const tabs = page.getByRole('navigation', { name: '插件页面' })
  await expect(tabs.getByRole('button', { name: '已安装' })).toHaveAttribute('aria-current', 'page')
  await tabs.getByRole('button', { name: '节点能力' }).dispatchEvent('click')
  await expect(page.getByRole('navigation', { name: '插件页面' }).getByRole('button', { name: '节点能力' })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('navigation', { name: '插件页面' }).getByRole('button', { name: '探索市场' }).dispatchEvent('click')
  await expect(page.getByRole('navigation', { name: '插件页面' }).getByRole('button', { name: '探索市场' })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('navigation', { name: '插件页面' }).getByRole('button', { name: '已安装' }).dispatchEvent('click')
  await page.getByRole('button', { name: '查看 E2E Provider 插件' }).click()
  await expect(page.getByText('声明的能力')).toBeVisible()
  await expect(page.getByText('Browser', { exact: true }).first()).toBeVisible()
})

test('plugin CTA carries capability context into Studio and can be removed', async ({ page }) => {
  await installPluginFixtures(page)
  await goAuthed(page, '/plugins')
  await page.getByRole('button', { name: '查看 E2E Provider 插件' }).click()
  await page.getByText('带着能力进入 Studio', { exact: true }).click()
  await expect(page).toHaveURL(/\/studio\?provider=e2e-provider&capability=/)
  await expect(page.getByRole('region', { name: '能力上下文' })).toContainText('e2e-provider')
  await expect(page.getByText(/目录 readiness 不等于 run-scoped admission/)).toBeVisible()
  const removeContext = page.getByRole('link', { name: '移除能力上下文' })
  await removeContext.click()
  await expect(page).toHaveURL(/\/studio(?:\?|$)/)
  await expect(page.getByRole('region', { name: '能力上下文' })).toHaveCount(0)
})


test('skill correction proposal can be dismissed and rollback is not stale after rollback', async ({ page }) => {
  let rolledBack = false
  let dismissed = false
  await page.route(api('/skills/skill-1'), (route) => {
    const evidence = rolledBack
      ? [{ event: 'corrected', from_version: 1, to_version: 2 }, { event: 'rolled_back', from_version: 2, to_version: 1 }]
      : dismissed
        ? [{ event: 'corrected', from_version: 1, to_version: 2 }, { event: 'correction_dismissed', from_version: 1, to_version: 2 }]
        : [{ event: 'corrected', from_version: 1, to_version: 2 }, { event: 'correction_proposed', trace_ids: ['trace-1'], prior_redistill_count: 0 }]
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { id: 'skill-1', name: 'Browser skill', domain: 'web', capability: 'browser', version: 2, status: 'active', enabled: true, evidence_count: 2, evidence },
      }),
    })
  })
  await page.route(api('/skills/skill-1/dismiss-correction'), async (route) => { dismissed = true; await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: {} }) }) })
  await page.route(api('/skills/skill-1/rollback'), async (route) => { rolledBack = true; await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: {} }) }) })
  await goAuthed(page, '/skills/skill-1')
  await expect(page).toHaveURL(/\/skills\/skill-1(?:\?.*)?$/, { timeout: 10000 })
  await expect(page.getByText('待复核的纠正建议')).toBeVisible()
  await page.getByRole('button', { name: '忽略纠正建议' }).click()
  await page.getByRole('button', { name: '确认忽略' }).click()
  await expect(page.getByText('待复核的纠正建议')).toHaveCount(0)
  const rollback = page.getByRole('button', { name: /回滚/ })
  await expect(rollback).toBeVisible()
  await rollback.click()
  await page.getByRole('button', { name: '确认回滚' }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: /回滚/ })).toHaveCount(0)
})


test('Action Center preserves canonical pane state while compatibility routes retain their filters', async ({
  page,
}) => {
  const { controlRequests, taskRequests } = await installActionCenterFixtures(page)
  await goAuthed(page, '/inbox?tab=pending')
  const workbench = page.getByTestId('inbox-workbench')
  const header = page.getByTestId('action-center-header')
  const queueViewport = page
    .getByTestId('inbox-queue-scroll')
    .locator('[data-slot="scroll-area-viewport"]')
  await expect(workbench).toBeVisible()
  await expect(queueViewport).toBeVisible()
  await header.evaluate((element) => {
    element.dataset.reviewIdentity = 'stable'
  })
  const queueScrollTop = await queueViewport.evaluate((element) => {
    element.scrollTop = 120
    element.dispatchEvent(new Event('scroll', { bubbles: true }))
    return element.scrollTop
  })
  const tabs = page.getByRole('navigation', { name: '相关视图' })

  await page.locator('#inbox-row-control-control-e2e-0').click()
  await page.getByRole('link', { name: '打开控制证据' }).click()
  await expect(page).toHaveURL(/\/inbox\?tab=controls$/)
  await expect(page.getByText('pause_collection').first()).toBeVisible()

  await tabs.getByRole('link', { name: '待处理' }).click()
  await expect(page).toHaveURL(/\/inbox\?tab=pending$/)
  await expect(header).toHaveAttribute('data-review-identity', 'stable')
  await expect
    .poll(() => queueViewport.evaluate((element) => element.scrollTop))
    .toBe(queueScrollTop)

  await tabs.getByRole('link', { name: '工作项' }).click()
  await expect(page).toHaveURL(/\/inbox\?tab=tasks$/)
  await expect(page.getByRole('region', { name: '任务历史' })).toBeVisible()
  await page.evaluate(() => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
  })
  await expect(page).toHaveURL(/\/inbox\?tab=tasks$/)

  await page.goto('/tasks?status=failed')
  await expect(page).toHaveURL(/\/inbox\?status=failed&tab=tasks$/)
  await expect(page.getByText('Failed source')).toBeVisible()
  await expect
    .poll(() => taskRequests.filter((status) => status === 'failed').length)
    .toBeGreaterThan(1)
  await expect(tabs.getByRole('link', { name: '通知规则' })).toHaveAttribute(
    'href',
    '/inbox?status=failed&tab=notifications',
  )

  await page.goto('/notifications?rule_id=e2e')
  await expect(page).toHaveURL(/\/inbox\?rule_id=e2e&tab=notifications$/)
  await expect(page.getByRole('region', { name: '通知规则' })).toBeVisible()

  await page.goto('/control/actions?outcome=pending')
  await expect(page).toHaveURL(/\/inbox\?outcome=pending&tab=controls$/)
  await expect(page.getByText('pause_collection').first()).toBeVisible()
  await expect
    .poll(() =>
      controlRequests.some(
        (query) => query.outcome === 'pending' && query.source_id === null && query.mode === null,
      ),
    )
    .toBeTruthy()
})
