import { expect, test } from '@playwright/test'

test('login page renders its local administrator credentials form', async ({ page }) => {
  await page.goto('/login')
  await expect(page.locator('[data-slot="card-title"]')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByLabel('用户名')).toHaveValue('admin')
  await expect(page.getByLabel('密码')).toBeVisible()
  await expect(page.getByLabel('管理员身份令牌')).toHaveCount(0)
  await expect(page.getByLabel('Fleet API 令牌（可选）')).toHaveCount(0)
})
