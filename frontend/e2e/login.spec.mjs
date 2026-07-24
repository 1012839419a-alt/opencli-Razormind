import { expect, test } from '@playwright/test'

test('login page renders its administrator credentials form', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByText('登录控制台')).toBeVisible()
  await expect(page.getByLabel('管理员身份令牌')).toBeVisible()
})
