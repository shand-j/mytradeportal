import { defineConfig } from "@playwright/test";

// Mobile regression suite against the LIVE staging API (no local backend).
// Sibling of playwright.config.regression.ts with two differences:
//
//   * The webServer starts only the Expo web harness — start-backend.sh is
//     not run, and the globalTeardown that stops the docker stack is omitted
//     (Playwright tears the Expo server down itself).
//   * The API target comes from E2E_API_BASE_URL (resolved by CI from the
//     Railway staging environment), never a localhost default.
//
// Each test group creates its own tenant via the setup token, so describes
// can run in parallel against shared staging; tests within a describe stay
// serial. Staging runs with RATE_LIMIT_ENABLED=false so the per-IP auth
// limit does not trip under many tenant logins from one CI runner IP.

const PORT = process.env.E2E_WEB_PORT ?? "8090";
const BASE_URL = `http://localhost:${PORT}`;
const API_BASE_URL = process.env.E2E_API_BASE_URL;
const WORKERS = Number(process.env.E2E_WORKERS ?? (process.env.CI ? 2 : 3));

if (!API_BASE_URL) {
  throw new Error(
    "E2E_API_BASE_URL is required for the staging config (e.g. https://api-staging-xxxx.up.railway.app)",
  );
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: /(regression|jobs|crm|settings|dashboard|messages|notifications)\.spec\.ts/,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: WORKERS,
  reporter: "list",
  timeout: 300_000,
  expect: { timeout: 30_000 },
  globalSetup: "./e2e/global-setup.ts",
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
    command: `pnpm exec expo start --web --port ${PORT} --clear`,
    url: BASE_URL,
    timeout: 300_000,
    reuseExistingServer: !process.env.CI,
    env: {
      EXPO_PUBLIC_API_BASE_URL: API_BASE_URL,
      // No white-label slug here: each test group creates its own tenant and
      // the helpers navigate to it via the generic marketplace entry.
      EXPO_PUBLIC_SETUP_TOKEN: process.env.E2E_STAGING_SETUP_TOKEN ?? "",
    },
  },
});
