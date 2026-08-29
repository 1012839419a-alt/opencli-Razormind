import { defineConfig } from "@playwright/test";

const port = process.env.PLAYWRIGHT_TEST_PORT ?? "3000";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: "chromium",
  },
  webServer: {
    command: `pnpm start --hostname 127.0.0.1 --port ${port}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
