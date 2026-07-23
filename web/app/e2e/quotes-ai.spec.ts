import { test, expect } from '@playwright/test';

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.example.com';
const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-password-123';

test.skip(!process.env.RUN_AI_E2E, 'AI E2E tests skipped by default; set RUN_AI_E2E=1 to run');

test.setTimeout(120000);

test('generate an AI draft quote from the quotes page', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel(/email/i).fill(adminEmail);
  await page.getByLabel(/password/i).fill(adminPassword);
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL('**/');

  await page.goto('/quotes');
  await expect(page).toHaveURL('/quotes');

  await page.getByTestId('generate-ai-quote').click();
  await expect(page.getByRole('heading', { name: /generate quote with ai/i })).toBeVisible();

  // Use a new lead so we do not depend on seeded contacts.
  await page.getByLabel(/new lead/i).check();
  await page.getByPlaceholder(/customer name/i).fill('AI Test Customer');
  await page.getByPlaceholder(/email/i).fill('ai-test@demo.local');

  await page.getByLabel(/job description/i).fill(
    'Replace a broken consumer unit and install 4 new double sockets in a 3 bedroom house'
  );

  await page.getByRole('button', { name: /generate draft/i }).click();

  // The backend creates the draft and redirects to the quote detail page.
  // Generation may take a few seconds while the LLM drafts line items.
  await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+$/, { timeout: 90000 });
  await expect(page.getByText('AI Test Customer')).toBeVisible();

  // A draft AI quote should have at least one line item.
  await expect(page.getByText(/£[0-9,]+/).first()).toBeVisible();

  // Download the generated PDF quote.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /download pdf/i }).click(),
  ]);
  const downloadPath = await download.path();
  await download.saveAs('test-results/quote.pdf');
  expect(downloadPath).toBeTruthy();
});
