// Light Playwright config for verifying the deployed landing/portal bundle of
// a Railway PR environment. Runs 3-5 critical public paths against
// TEST_LANDING_URL — no Docker stack, no auth fixtures, chromium only.
//
//   pnpm exec playwright test --config playwright.pr.config.ts
//
// Contrast with playwright.config.ts, which boots the full local Docker stack
// and drives the back-office SPA — far too heavy for PR-environment CI.

import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.TEST_LANDING_URL;

if (!baseURL) {
  throw new Error('TEST_LANDING_URL is required (e.g. the PR environment landing URL)');
}

export default defineConfig({
  testDir: './e2e/pr-env',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 30 * 1000,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
