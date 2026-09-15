// PR-environment smoke tests for the landing/portal bundle (see
// playwright.pr.config.ts). These run against a deployed URL
// (TEST_LANDING_URL) and only ever exercise public, deterministic pages —
// no form submissions, so no LLM/Paddle/Stripe calls are triggered.
import { expect, test } from '@playwright/test';

const BOGUS_TOKEN = '0'.repeat(32);

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

test('pay page shows the invalid-link state for a bogus token', async ({ page }) => {
  await page.goto(`/pay/${BOGUS_TOKEN}`);
  await expect(page.getByRole('alert')).toContainText(/link is invalid or has expired/i);
});

test('quote page shows the invalid-link state for a bogus token', async ({ page }) => {
  await page.goto(`/quote/${BOGUS_TOKEN}`);
  await expect(page.getByRole('alert')).toContainText(/link is invalid or has expired/i);
});
