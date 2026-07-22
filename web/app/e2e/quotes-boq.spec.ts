import { test, expect } from '@playwright/test';

test.setTimeout(240000);

test('generate a BoQ-driven AI quote and save artifacts', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel(/email/i).fill('admin@demo.local');
  await page.getByLabel(/password/i).fill('password123');
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL('**/');

  await page.goto('/quotes');
  await expect(page).toHaveURL('http://demo.localhost:3000/quotes');

  await page.getByTestId('generate-ai-quote').click();
  await expect(page.getByRole('heading', { name: /generate quote with ai/i })).toBeVisible();

  // Enable the OpenConstructionERP / BoQ path.
  await page.getByTestId('use-ocerp').check();

  // Use a new lead so we do not depend on seeded contacts.
  await page.getByLabel(/new lead/i).check();
  await page.getByPlaceholder(/customer name/i).fill('BoQ Test Customer');
  await page.getByPlaceholder(/email/i).fill('boq-test@demo.local');

  await page.getByLabel(/job description/i).fill(
    'Full rewire of a 4 bedroom detached house including new consumer unit, 25 downlights, 12 double sockets, 6 TV points, and external EV charger'
  );

  await page.getByRole('button', { name: /generate draft/i }).click();

  // The backend creates the draft and redirects to the quote detail page.
  // BoQ generation may take a few seconds while the microservice drafts line items.
  await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+$/, { timeout: 150000 });
  await expect(page.getByText('BoQ Test Customer')).toBeVisible();
  await expect(page.getByText(/£[0-9,]+/).first()).toBeVisible();

  // The BoQ section should be visible.
  const boqSection = page.getByRole('heading', { name: /bill of quantities/i });
  await expect(boqSection).toBeVisible();

  // Every BoQ must clearly state it is an indicative bill and attribute suppliers.
  await expect(page.getByText(/indicative bill of quantities/i)).toBeVisible();
  await expect(page.getByText(/prices sourced from/i)).toBeVisible();

  // The BoQ table should contain itemised components, not a generic "rewire" line.
  const boqTable = boqSection.locator('..').locator('..').locator('table');
  await expect(boqTable.getByText(/consumer unit/i).first()).toBeVisible();
  await expect(boqTable.getByText(/socket|tv point/i).first()).toBeVisible();
  await expect(boqTable.getByText(/downlight|light fitting/i).first()).toBeVisible();
  await expect(boqTable.getByText(/ev charge|cable/i).first()).toBeVisible();
  await expect(boqTable.getByText(/labour|electrician/i).first()).toBeVisible();

  // The customer-facing quote should reflect the BoQ total (non-zero).
  await expect(page.locator('div.text-2xl.font-bold').getByText(/£[0-9,]+/).first()).toBeVisible();

  // Save a screenshot of the generated quote detail page.
  await page.screenshot({ path: 'test-results/boq-quote-detail.png', fullPage: true });

  // Download the generated PDF quote.
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /download pdf/i }).click(),
  ]);
  const downloadPath = await download.path();
  await download.saveAs('test-results/boq-quote.pdf');
  expect(downloadPath).toBeTruthy();
});
