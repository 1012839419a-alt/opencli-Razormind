import { expect, test } from '@playwright/test'

const TOKEN_KEY = 'opencli.bootstrapIdentityToken'

const identity = {
  subject: 'test-admin',
  email: null,
  name: 'Test Admin',
  username: 'test-admin',
  picture: null,
  is_platform_admin: true,
  auth_method: 'bootstrap',
}

const response = (data) => ({
  contentType: 'application/json',
  body: JSON.stringify({ success: true, data }),
})

async function retainTestIdentity(page) {
  await page.addInitScript(
    ({ key }) => sessionStorage.setItem(key, 'retained-test-token'),
    { key: TOKEN_KEY },
  )
}

async function fulfillSystemApi(route, counters = {}) {
  const path = new URL(route.request().url()).pathname
  if (path.endsWith('/system/config')) {
    counters.systemConfig = (counters.systemConfig ?? 0) + 1
    await route.fulfill(
      response({ collection_mode: 'local', task_executor: 'local', image_tag: '0.4.1' }),
    )
    return
  }
  if (path.endsWith('/workers/chrome-pool')) {
    await route.fulfill(response({ endpoints: [], total: 0, available: 0 }))
    return
  }
  if (path.endsWith('/workers/celery-stats')) {
    await route.fulfill(response({ error: 'local executor' }))
    return
  }
  await route.fulfill(response([]))
}

test('mounted auth recovery retains the token and returns to the requested route', async ({ page }) => {
  await retainTestIdentity(page)
  let identityCalls = 0

  await page.route('**/health', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) }),
  )
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) {
      identityCalls += 1
      if (identityCalls === 1) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'API is starting' }),
        })
      } else {
        await route.fulfill(response(identity))
      }
      return
    }
    await fulfillSystemApi(route)
  })

  await page.goto('/system')
  await expect(page.getByText('API 服务正在恢复')).toBeVisible()
  await expect(page.getByRole('heading', { name: '系统与运维' })).toBeVisible()
  expect(identityCalls).toBe(2)
  await expect
    .poll(() => page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY))
    .toBe('retained-test-token')
})

test('mounted auth recovery clears the token only after explicit identity rejection', async ({ page }) => {
  await retainTestIdentity(page)
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'identity rejected' }),
    }),
  )

  await page.goto('/system')
  await expect(page).toHaveURL(/\/login\?returnTo=/)
  await expect
    .poll(() => page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY))
    .toBeNull()
})

test('mounted auth recovery retains an incompatible request without polling health', async ({ page }) => {
  await retainTestIdentity(page)
  let healthCalls = 0
  await page.route('**/health', async (route) => {
    healthCalls += 1
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) })
  })
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'frontend contract mismatch' }),
    }),
  )

  await page.goto('/system')
  await expect(page.getByText('身份校验需要处理')).toBeVisible()
  expect(healthCalls).toBe(0)
  expect(await page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY)).toBe(
    'retained-test-token',
  )
})

test('restart interaction requires a new API instance before refresh and can be reset', async ({ page }) => {
  await retainTestIdentity(page)
  const counters = { systemConfig: 0 }
  let healthCalls = 0

  await page.route('**/health', async (route) => {
    healthCalls += 1
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', instance_id: healthCalls === 1 ? 'old-api' : 'new-api' }),
    })
  })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) {
      await route.fulfill(response(identity))
      return
    }
    if (path.endsWith('/browsers/restart-api')) {
      await route.fulfill(response({ restarting: true, instance_id: 'old-api' }))
      return
    }
    await fulfillSystemApi(route, counters)
  })

  await page.goto('/system')
  await expect(page.getByRole('button', { name: '重启 API 服务' })).toBeVisible()
  await page.getByRole('button', { name: '重启 API 服务' }).click()
  await page.getByLabel(/请输入 RESTART 以确认/).fill('RESTART')
  await page.getByRole('button', { name: '确认重启' }).click()

  const restartAgain = page.getByRole('button', { name: '再次重启' })
  await expect(restartAgain).toBeVisible()
  await expect.poll(() => counters.systemConfig).toBeGreaterThanOrEqual(2)
  expect(healthCalls).toBeGreaterThanOrEqual(2)
  await restartAgain.click()
  await expect(page.getByRole('button', { name: '重启 API 服务' })).toBeVisible()
})
