import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL: 'http://127.0.0.1:3000',
    browserName: 'chromium',
  },
  webServer: {
    command: 'node .next/standalone/server.js',
    env: {
      HOSTNAME: '127.0.0.1',
      NODE_ENV: 'production',
      PORT: '3000',
    },
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
