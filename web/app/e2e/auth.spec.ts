import { test, expect } from '@playwright/test';

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.example.com';
const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-password-123';
const tenantSlug = process.env.E2E_TENANT_SLUG ?? 'demo';

test('admin can log in and interact with the dashboard', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel(/business slug/i).fill(tenantSlug);
  await page.getByLabel(/email/i).fill(adminEmail);
  await page.getByLabel(/password/i).fill(adminPassword);
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL('**/');
  await expect(page).toHaveURL('/');
  await expect(page.getByText('Revenue This Month')).toBeVisible();

  // Dashboard should render KPI cards instead of going white
  await expect(page.getByText('Revenue This Month')).toBeVisible();

  // Interact with sidebar navigation
  await page.getByRole('link', { name: /quotes/i }).click();
  await expect(page).toHaveURL('/quotes');
  await expect(page.getByRole('heading', { name: /quotes/i, level: 1 })).toBeVisible();

  // AI Insights page should render without a white-screen crash
  await page.getByRole('link', { name: /ai insights/i }).click();
  await expect(page).toHaveURL('/ai-insights');
  await expect(page.getByRole('heading', { name: /ai insights/i, level: 1 })).toBeVisible();
});
