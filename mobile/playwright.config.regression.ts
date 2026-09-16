import { defineConfig } from "@playwright/test";

// Full mobile regression suite. Starts the FastAPI backend stack once, seeds
// no shared tenant data (each test group creates its own tenant for
// isolation), then starts the Expo web harness. Describes can run in
// parallel across workers because each has its own tenant + backend state;
// tests within a describe stay serial (they share the tenant seeded in
// ``beforeAll``). The `E2E_WORKERS` env var lets ops tune concurrency vs
// Kimi/Moonshot rate limits.

const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;
const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8002";
const WORKERS = Number(process.env.E2E_WORKERS ?? (process.env.CI ? 2 : 3));

export default defineConfig({
  testDir: "./e2e",
  testMatch: /(regression|jobs|crm|settings|dashboard|messages|notifications|emails|rounding|branding|blocked|ai-metadata|customer-invoices)\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: WORKERS,
  reporter: "list",
  timeout: 300_000,
  expect: { timeout: 30_000 },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/orchestration/global-teardown.js",
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
    command: `bash ./e2e/orchestration/start-backend.sh && pnpm exec expo start --web --port ${PORT} --clear`,
    url: BASE_URL,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    env: {
      EXPO_PUBLIC_API_BASE_URL: API_BASE_URL,
      // No white-label slug here: each test group creates its own tenant and
      // the helpers navigate to it via the generic marketplace entry.
      EXPO_PUBLIC_SETUP_TOKEN: process.env.E2E_SETUP_TOKEN ?? "",
    },
  },
});
