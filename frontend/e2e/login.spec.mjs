import { expect, test } from '@playwright/test'

test('login page renders its administrator credentials form', async ({ page }) => {
  await page.route('**/api/v1/auth/local/status', async (route) => {
    await route.fulfill({ json: { data: { configured: false } } })
  })
  await page.goto('/login')
  await expect(page.getByText('登录控制台')).toBeVisible()
  await expect(page.getByLabel('首次部署令牌')).toBeVisible()
  await expect(page.getByLabel('管理员密码', { exact: true })).toBeVisible()
  await expect(page.getByLabel('确认管理员密码')).toBeVisible()
})

test('configured local administrator sees the returning login form', async ({ page }) => {
  await page.route('**/api/v1/auth/local/status', async (route) => {
    await route.fulfill({ json: { data: { configured: true } } })
  })
  await page.goto('/login')
  await expect(page.getByText('本地管理员登录')).toBeVisible()
  await expect(page.getByLabel('管理员密码', { exact: true })).toBeVisible()
  await expect(page.getByLabel('首次部署令牌')).toHaveCount(0)
  await expect(page.getByLabel('确认管理员密码')).toHaveCount(0)
})
