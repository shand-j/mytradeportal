// Playwright config for the tenant customer-portal e2e suite.
//
// Runs the specs under ./e2e against a DEPLOYED landing bundle + staging API
// (no local Docker stack — the portal needs the full backend, LLM and Mailpit
// to be meaningful). Portal mode is forced with the `?slug=` host override
// (see src/portal/host.ts and docs/e2e-coverage-gaps.md "Portal test
// strategy"), so any landing origin works with no DNS/hosts-file changes.
//
//   TEST_API_BASE_URL=https://api-staging-cced.up.railway.app \
//   TEST_SETUP_TOKEN=… MAILPIT_URL=… MAILPIT_BASIC_AUTH=… \
//   pnpm exec playwright test --config playwright.portal.config.ts
//
// Env:
//   TEST_LANDING_URL  landing origin under test (defaults to staging)
//   TEST_API_BASE_URL staging API (tenant bootstrap + seeding)
//   TEST_SETUP_TOKEN  setup token for POST /tenants bootstrap
//   MAILPIT_URL / MAILPIT_BASIC_AUTH  staging Mailpit (email assertions)
//   TEST_PADDLE_WEBHOOK_SECRET  subscription-state drive (gating spec)

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 120 * 1000,
  expect: { timeout: 20_000 },
  reporter: "list",
  use: {
    baseURL:
      process.env.TEST_LANDING_URL ?? "https://landing-staging-192c.up.railway.app",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
