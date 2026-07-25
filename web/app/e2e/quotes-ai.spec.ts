import { test, expect } from './fixtures';
import { ensureDefaultAdminSession } from './helpers';

test.skip(!process.env.RUN_AI_E2E, 'AI E2E tests skipped by default; set RUN_AI_E2E=1 to run');

test.setTimeout(120000);

test('generate an AI draft quote from the quotes page', async ({ page }) => {
  await ensureDefaultAdminSession(page);

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

  const generateResponsePromise = page.waitForResponse(
    (res) => res.url().includes('/quotes/generate') && res.request().method() === 'POST',
    { timeout: 90_000 }
  );
  await page.getByRole('button', { name: /generate draft/i }).click();
  const generateResponse = await generateResponsePromise;

  if (!generateResponse.ok()) {
    // In production-like validation, AI dependencies may be unavailable.
    expect(generateResponse.status()).toBe(503);
    await expect(page).toHaveURL(/\/quotes$/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: /generate quote with ai/i })).toBeVisible();
    return;
  }

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
