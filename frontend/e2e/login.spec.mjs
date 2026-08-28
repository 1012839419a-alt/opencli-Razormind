import { expect, test } from '@playwright/test'

test('login page mounts its WebGL2 backdrop and renders local administrator credentials', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByText('登录控制台')).toBeVisible()
  await expect(page.getByLabel('用户名')).toHaveValue('admin')
  await expect(page.getByLabel('密码')).toBeVisible()
  await expect(page.getByLabel('管理员身份令牌')).toHaveCount(0)
  await expect(page.getByLabel('Fleet API 令牌（可选）')).toHaveCount(0)
  await expect(page.locator('[data-gpu-surface="login-background"]'))
    .toHaveAttribute('data-gpu-backend', 'webgl2')
})

test('login page keeps its static backdrop and form usable without WebGL2', async ({ page }) => {
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

  await page.goto('/login')
  await expect(page.locator('[data-gpu-surface="login-background"]'))
    .toHaveAttribute('data-gpu-backend', 'fallback')
  await expect(page.locator('[data-login-static-background]')).toBeVisible()
  await expect(page.getByLabel('用户名')).toHaveValue('admin')
  await expect(page.getByLabel('密码')).toBeVisible()
})

test('login SSR output retains the pending fallback without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  try {
    await page.goto('/login')
    const pendingSurface = page.locator('[data-gpu-surface="login-background"]').first()
    await expect(pendingSurface).toHaveAttribute('data-gpu-backend', 'pending')
    await expect(pendingSurface.locator('[data-login-static-background]')).toHaveCount(1)
    expect(pageErrors).toEqual([])
  } finally {
    await context.close()
  }
})

test('login releases its GPU backdrop for reduced motion while keeping the form usable', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('[data-gpu-surface="login-background"]'))
    .toHaveAttribute('data-gpu-backend', 'webgl2')

  await page.emulateMedia({ reducedMotion: 'reduce' })

  await expect(page.locator('[data-gpu-surface="login-background"]'))
    .toHaveAttribute('data-gpu-backend', 'fallback')
  await expect(page.locator('[data-login-static-background]')).toBeVisible()
  await expect(page.getByLabel('用户名')).toHaveValue('admin')
  await expect(page.getByLabel('密码')).toBeVisible()
})

test('login recreates its GPU backdrop after a WebGL context loss', async ({ page }) => {
  await page.goto('/login')
  const surface = page.locator('[data-gpu-surface="login-background"]')
  await expect(surface).toHaveAttribute('data-gpu-backend', 'webgl2')

  const canvas = surface.locator('canvas').first()
  await expect(canvas).toBeAttached()
  await page.waitForTimeout(50)
  await canvas.dispatchEvent('webglcontextlost', { cancelable: true })

  await expect(surface).toHaveAttribute('data-gpu-fallback-reason', 'context-lost')
  await expect(page.locator('[data-login-static-background]')).toBeVisible()
  await expect(surface).toHaveAttribute('data-gpu-backend', 'webgl2')
  await expect(surface.locator('canvas').first()).toBeAttached()
})
