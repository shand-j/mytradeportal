import { defineConfig, devices } from '@playwright/test';

/**
 * Production smoke-test configuration.
 *
 * Usage:
 *   E2E_BASE_URL=https://web-production-XXXX.up.railway.app \
 *   E2E_ADMIN_BASE_URL=https://admin-production-XXXX.up.railway.app \
 *   E2E_ADMIN_USERNAME=e2e-superadmin \
 *   E2E_ADMIN_PASSWORD=... \
 *   E2E_ADMIN_EMAIL=... \
 *   pnpm exec playwright test --config=playwright.config.prod.ts
 *
 * Do NOT start the local Docker stack; this config talks to the deployed
 * production services. Runs with a single worker to avoid clobbering shared
 * production data.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'https://web-production-0919a.up.railway.app';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: true,
  retries: 1,
  workers: 1,
  reporter: 'list',
  globalSetup: './e2e/global-setup',
  use: {
    baseURL,
    storageState: 'playwright/.auth/admin.json',
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
