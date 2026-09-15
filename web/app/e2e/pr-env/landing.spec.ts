// PR-environment smoke tests for the landing/portal bundle (see
// playwright.pr.config.ts). These run against a deployed URL
// (TEST_LANDING_URL) and only ever exercise public, deterministic pages —
// no form submissions, so no LLM/Paddle/Stripe calls are triggered.
import { expect, test } from '@playwright/test';

const BOGUS_TOKEN = '0'.repeat(32);

// The bogus-token pages must reach a terminal, non-loading state. The
// expected state is "invalid link"; an error alert is also accepted because
// PR environments inherit production's literal VITE_API_URL (the PR landing
// calls the PRODUCTION api, whose CORS allowlist rejects the PR origin), so
// the fetch can fail until the platform switches VITE_API_URL to a Railway
// reference variable. See docs/ci-pr-environments.md (Limitations).
const TERMINAL_STATE = /link is invalid or has expired|check your connection|try again later/i;

test('landing home loads with hero, pricing and quote demo', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveTitle(/My Trade Portal/i);
  await expect(page.getByRole('heading', { name: /your trade/i })).toBeVisible();

  // Interactive AI quote demo (rendered inside the hero; the test only checks
  // the UI is mounted — it never submits, so no demo/LLM call is made).
  await expect(page.locator('#demo-description')).toBeVisible();

  // Pricing section renders with its headline.
  await expect(page.locator('#pricing')).toContainText(/every price on the page/i);
});

test('fair-use policy page renders', async ({ page }) => {
  await page.goto('/fair-use');
  await expect(page).toHaveTitle(/fair-use/i);
  await expect(page.getByRole('heading', { name: /fair/i }).first()).toBeVisible();
});

test('pay page shows a terminal state for a bogus token', async ({ page }) => {
  await page.goto(`/pay/${BOGUS_TOKEN}`);
  await expect(page.getByRole('alert')).toContainText(TERMINAL_STATE);
});

test('quote page shows a terminal state for a bogus token', async ({ page }) => {
  await page.goto(`/quote/${BOGUS_TOKEN}`);
  await expect(page.getByRole('alert')).toContainText(TERMINAL_STATE);
});
