import { defineConfig, devices } from '@playwright/test';

/**
 * Production smoke-test configuration.
 *
 * This config creates a fresh tenant via the Django admin UI using the
 * production superuser, exercises the back-office UI, and relies on an
 * external teardown step (see .github/workflows/smoke-production.yml) to
 * remove the test data.
 *
 * Usage:
 *   E2E_BASE_URL=https://web-production-XXXX.up.railway.app \
 *   E2E_ADMIN_BASE_URL=https://admin-production-XXXX.up.railway.app \
 *   E2E_DJANGO_ADMIN_USERNAME=superadmin \
 *   E2E_DJANGO_ADMIN_PASSWORD=... \
 *   pnpm exec playwright test --config=playwright.config.prod-smoke.ts
 */
const baseURL = process.env.E2E_BASE_URL ?? 'https://web-production-0919a.up.railway.app';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'prod-smoke.spec.ts',
  fullyParallel: false,
  forbidOnly: true,
  retries: 1,
  workers: 1,
  reporter: 'list',
  // No global setup: the smoke test logs in dynamically inside beforeAll.
  globalSetup: undefined,
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No local web server for production runs.
  webServer: undefined,
});
