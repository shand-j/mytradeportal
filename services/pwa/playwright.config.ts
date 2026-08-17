import { defineConfig } from "@playwright/test";

// Trade connected-mode smoke: the app points at the real API with no business
// slug, so the entry screen exposes trade login + registration. Runs on its own
// Expo build; the white-label suite uses a separate config/build.

const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;
const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
const SETUP_TOKEN = process.env.E2E_SETUP_TOKEN ?? "e2e-setup-token";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /connected-smoke\.spec\.ts/,
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
      // The web build is a test harness for the native app, which has no CORS.
      // Disable web security so cross-origin calls to the API behave like native.
      args: ["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"],
    },
  },
  webServer: {
    // --clear guarantees a fresh bundle with this config's EXPO_PUBLIC_* env
    // (the sibling white-label config reuses the same port with different env).
    command: `pnpm exec expo start --web --port ${PORT} --clear`,
    url: BASE_URL,
    timeout: 240_000,
    reuseExistingServer: !process.env.CI,
    env: {
      EXPO_PUBLIC_API_BASE_URL: API_BASE_URL,
      EXPO_PUBLIC_SETUP_TOKEN: SETUP_TOKEN,
    },
  },
});
