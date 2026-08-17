import { defineConfig } from "@playwright/test";

// White-label smoke: a per-tenant build with EXPO_PUBLIC_BUSINESS_SLUG set. The
// app fetches that business's public config on launch and themes itself, opening
// on the branded customer entry instead of the generic 6-digit code screen.
//
// Runs on the same port as the trade config but as a separate invocation, so the
// two Expo builds never run concurrently.

const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;
const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
const BUSINESS_SLUG = process.env.E2E_BUSINESS_SLUG ?? "demo";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /white-label\.spec\.ts/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  timeout: 240_000,
  expect: { timeout: 20_000 },
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    viewport: { width: 402, height: 874 },
    launchOptions: {
      args: ["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"],
    },
  },
  webServer: {
    command: `pnpm exec expo start --web --port ${PORT} --clear`,
    url: BASE_URL,
    timeout: 240_000,
    reuseExistingServer: !process.env.CI,
    env: {
      EXPO_PUBLIC_API_BASE_URL: API_BASE_URL,
      EXPO_PUBLIC_BUSINESS_SLUG: BUSINESS_SLUG,
    },
  },
});
