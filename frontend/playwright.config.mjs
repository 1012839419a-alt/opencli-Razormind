import { defineConfig } from '@playwright/test'

function resolveSmokePort(value) {
  const port = value ?? '3101'
  if (!/^[1-9]\d{0,4}$/.test(port) || Number(port) > 65535) {
    throw new Error('PLAYWRIGHT_SMOKE_PORT must be an integer from 1 through 65535')
  }
  return port
}

const smokePort = resolveSmokePort(process.env.PLAYWRIGHT_SMOKE_PORT)
const smokeUrl = `http://127.0.0.1:${smokePort}`

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: smokeUrl,
    browserName: 'chromium',
  },
  webServer: {
    command: `pnpm start --hostname 127.0.0.1 --port ${smokePort}`,
    url: smokeUrl,
    reuseExistingServer: process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER === '1',
    timeout: 30_000,
  },
})
