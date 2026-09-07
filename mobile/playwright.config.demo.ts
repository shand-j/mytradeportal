import { defineConfig } from "@playwright/test";

/**
 * Demo suite — Kimi-driven customer chat E2E.
 *
 * NOT run as part of standard regression. Kick it off explicitly:
 *   pnpm exec playwright test --config=playwright.config.demo.ts
 *
 * Reuses the mobile backend stack (docker-compose.mobile.yml) started by the
 * regression config's orchestration script.
 */

// Absolute path to this file's directory (Playwright loads configs as CJS, so
// ``__dirname`` is available at runtime; declared here to satisfy TypeScript
// without pulling in @types/node).
declare const __dirname: string;
const CONFIG_DIR = __dirname;
const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;
const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8002";

export default defineConfig({
  testDir: `${CONFIG_DIR}/e2e`,
  testMatch: /demo-.*\.spec\.ts/,
  grep: /@demo/,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  timeout: 600_000,
  expect: { timeout: 30_000 },
  globalSetup: `${CONFIG_DIR}/e2e/global-setup.ts`,
  globalTeardown: `${CONFIG_DIR}/e2e/orchestration/global-teardown.js`,
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on",
    viewport: { width: 402, height: 874 },
    launchOptions: {
      args: ["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"],
    },
  },
  webServer: {
    command: `bash ${CONFIG_DIR}/e2e/orchestration/start-backend.sh && cd ${CONFIG_DIR} && pnpm exec expo start --web --port ${PORT} --clear`,
    url: BASE_URL,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    env: {
      EXPO_PUBLIC_API_BASE_URL: API_BASE_URL,
      EXPO_PUBLIC_SETUP_TOKEN: process.env.E2E_SETUP_TOKEN ?? "",
    },
  },
});
