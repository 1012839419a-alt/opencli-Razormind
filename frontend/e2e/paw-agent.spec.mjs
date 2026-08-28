import { expect, test } from '@playwright/test'

const api = (path) => `**/api/v1${path}`

async function login(page) {
  await page.goto('/login?returnTo=%2Fagents')
  await page.getByLabel('用户名').fill('admin')
  await page.getByLabel('密码').fill('admin')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/agents(?:\?.*)?$/)
}

test('PAW agent form exposes governed config and blocks blank prompt submission', async ({ page }) => {
  let submitted = null
  await page.route(api('/auth/login'), (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { access_token: 'e2e-token', token_type: 'bearer' } }) }))
  await page.route(api('/auth/me'), (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { subject: 'e2e', name: 'E2E', is_platform_admin: true } }) }))
  await page.route(api('/agents'), async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }) })
    submitted = route.request().postDataJSON()
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: { id: 'paw-e2e', ...submitted, created_at: '2026-08-28T00:00:00Z', updated_at: '2026-08-28T00:00:00Z' } }) })
  })
  await page.route(api('/providers'), (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ success: true, data: [] }) }))

  await login(page)
  await page.getByRole('button', { name: '添加 Agent' }).click()
  await page.getByLabel('处理器类型').click()
  await page.getByRole('option', { name: 'PAW 本地富化' }).click()
  await expect(page.getByText('使用固定、离线的 PAW sidecar')).toBeVisible()
  await expect(page.getByText('PAW 必须使用非空的短提示词模板。')).toBeVisible()
  await page.getByLabel('名称').fill('PAW fixture')
  await page.getByRole('button', { name: '创建 Agent' }).click()
  await expect.poll(() => submitted).toBeNull()
  await page.getByLabel('提示词模板').fill('Classify {{title}}')
  await page.getByText('高级设置').click()
  await page.getByLabel('处理器配置（JSON，可选）').fill('{"max_tokens": 8, "output_schema": {"type": "object"}}')
  await page.getByRole('button', { name: '创建 Agent' }).click()
  await expect.poll(() => submitted).toMatchObject({
    processor_type: 'paw',
    prompt_template: 'Classify {{title}}',
    processor_config: { max_tokens: 8, output_schema: { type: 'object' } },
  })
})
