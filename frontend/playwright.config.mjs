import { defineConfig } from '@playwright/test'

const requestedPort = Number(process.env.PLAYWRIGHT_PORT ?? '3000')
if (!Number.isInteger(requestedPort) || requestedPort < 1 || requestedPort > 65535) {
  throw new Error('PLAYWRIGHT_PORT must be an integer between 1 and 65535')
}
const port = String(requestedPort)

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
  },
  webServer: {
    command: `pnpm start --hostname 127.0.0.1 --port ${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
