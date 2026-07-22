import { test, expect } from '@playwright/test';

test('admin can log in and interact with the dashboard', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel(/email/i).fill('admin@demo.local');
  await page.getByLabel(/password/i).fill('password123');
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL('**/');
  await expect(page).toHaveURL('http://demo.localhost:3000/');
  await expect(page.getByText('Demo Admin')).toBeVisible();

  // Dashboard should render KPI cards instead of going white
  await expect(page.getByText('Revenue This Month')).toBeVisible();

  // Interact with sidebar navigation
  await page.getByRole('link', { name: /quotes/i }).click();
  await expect(page).toHaveURL('http://demo.localhost:3000/quotes');
  await expect(page.getByRole('heading', { name: /quotes/i, level: 1 })).toBeVisible();

  // AI Insights page should render without a white-screen crash
  await page.getByRole('link', { name: /ai insights/i }).click();
  await expect(page).toHaveURL('http://demo.localhost:3000/ai-insights');
  await expect(page.getByRole('heading', { name: /ai insights/i, level: 1 })).toBeVisible();
});
