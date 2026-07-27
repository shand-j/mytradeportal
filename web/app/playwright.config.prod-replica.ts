import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL ?? 'http://demo.localhost:3000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: 1,
  reporter: 'list',
  globalSetup: './e2e/global-setup',
  use: {
    baseURL,
    storageState: 'playwright/.auth/admin.json',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: './e2e/start-stack.sh',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 300 * 1000,
  },
});
