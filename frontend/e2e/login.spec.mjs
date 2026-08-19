import { expect, test } from '@playwright/test'

const identity = {
  subject: 'local:owner',
  email: null,
  name: '家庭管理员',
  username: 'owner',
  picture: null,
  is_platform_admin: true,
  auth_method: 'local',
}

const response = (data) => ({ success: true, data })

test('uninitialized device creates its local owner with a one-time claim code', async ({ page }) => {
  let setupRequest
  let csrfHeader

  await page.route('**/api/v1/auth/status', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(
        response({
          initialized: false,
          oidc_enabled: false,
          local_login_enabled: true,
          recovery_enabled: false,
        }),
      ),
    }),
  )
  await page.route('**/api/v1/auth/setup', async (route) => {
    setupRequest = route.request().postDataJSON()
    csrfHeader = route.request().headers()['x-opencli-csrf']
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(response(identity)),
    })
  })

  await page.goto('/login?returnTo=/login')

  await expect(page.getByRole('heading', { name: '设置此设备' })).toBeVisible()
  await expect(page.getByLabel('设备认领码')).toBeVisible()
  await expect(page.getByPlaceholder('BOOTSTRAP_ADMIN_TOKEN')).toHaveCount(0)
  await expect(page.getByPlaceholder('API_AUTH_TOKEN')).toHaveCount(0)

  await page.getByLabel('设备认领码').fill('claim-once')
  await page.getByLabel('管理员用户名').fill('owner')
  await page.getByLabel('显示名称（可选）').fill('家庭管理员')
  await page.getByLabel('管理员密码').fill('owner-password')
  await page.getByLabel('确认密码').fill('owner-password')
  await expect(page.getByRole('checkbox', { name: '记住此设备' })).toBeChecked()
  await page.getByRole('button', { name: '完成设置并进入控制台' }).click()

  await expect.poll(() => setupRequest).toEqual({
    claim_code: 'claim-once',
    username: 'owner',
    display_name: '家庭管理员',
    password: 'owner-password',
    remember_device: true,
  })
  expect(csrfHeader).toBe('1')
})

test('initialized device defaults to local account login without operator tokens', async ({ page }) => {
  let loginRequest
  let csrfHeader

  await page.route('**/api/v1/auth/status', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(
        response({
          initialized: true,
          oidc_enabled: false,
          local_login_enabled: true,
          recovery_enabled: true,
        }),
      ),
    }),
  )
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not authenticated' }),
    }),
  )
  await page.route('**/api/v1/auth/login', async (route) => {
    loginRequest = route.request().postDataJSON()
    csrfHeader = route.request().headers()['x-opencli-csrf']
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(response(identity)),
    })
  })

  await page.goto('/login?returnTo=/login')

  await expect(page.getByRole('heading', { name: '登录控制台' })).toBeVisible()
  await expect(page.getByText('使用本机管理员账号登录。')).toBeVisible()
  await expect(page.getByText('当前未配置组织登录')).toHaveCount(0)
  await expect(page.getByText('Fleet API 令牌（可选）')).toHaveCount(0)
  await expect(page.getByText('管理员身份令牌')).toHaveCount(0)

  await page.getByLabel('管理员用户名').fill('owner')
  await page.getByLabel('密码').fill('owner-password')
  await page.getByRole('checkbox', { name: '记住此设备' }).uncheck()
  await page.getByRole('button', { name: '登录', exact: true }).click()

  await expect.poll(() => loginRequest).toEqual({
    username: 'owner',
    password: 'owner-password',
    remember_device: false,
  })
  expect(csrfHeader).toBe('1')
  await expect(page.getByText('紧急恢复')).toBeVisible()
})
