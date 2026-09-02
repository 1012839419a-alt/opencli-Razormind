import { defineConfig } from "@playwright/test";

const port = process.env.PLAYWRIGHT_TEST_PORT ?? "3000";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
  },
  webServer: {
    command: "node scripts/start-standalone.mjs",
    env: {
      ...process.env,
      HOSTNAME: "127.0.0.1",
      PORT: port,
    },
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
