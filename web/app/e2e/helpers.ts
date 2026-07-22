import type { Page } from '@playwright/test';

export async function createCustomer(
  page: Page,
  testId: string,
  overrides: { firstName?: string; lastName?: string; phone?: string } = {}
): Promise<string> {
  const firstName = overrides.firstName ?? `E2E`;
  const lastName = overrides.lastName ?? `Customer-${testId}`;
  const customerName = `${firstName} ${lastName}`;

  await page.goto('/customers');
  await page.getByRole('button', { name: /add customer/i }).click();

  await page.getByPlaceholder(/first name/i).fill(firstName);
  await page.getByPlaceholder(/last name/i).fill(lastName);
  await page.getByPlaceholder(/email/i).fill(`e2e-${testId}@demo.local`);
  await page.getByPlaceholder(/phone/i).fill(overrides.phone ?? '07700 000000');
  await page.getByPlaceholder(/address/i).fill('1 Test Road');
  await page.getByPlaceholder(/postcode/i).fill('TE1 1ST');

  await page.getByRole('button', { name: /save customer/i }).click();
  await page.locator('.rounded-xl', { hasText: customerName }).first().waitFor();

  return customerName;
}

export async function createQuote(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `QUOTE-${testId}`;

  await page.goto('/quotes');
  await page.getByRole('button', { name: /new quote/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create quote/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.getByPlaceholder(/service type/i).fill('Consumer unit replacement');
  await modal.getByPlaceholder(/property address/i).fill('1 Test Road, TE1 1ST');
  await modal.getByPlaceholder(/description/i).fill('Labour and materials');
  await modal.locator('input[type="number"]').nth(1).fill('250');

  await modal.getByRole('button', { name: /create quote/i }).click();
  await page.getByRole('link', { name: reference }).first().waitFor();

  return reference;
}

export async function openQuoteDetail(page: Page, reference: string) {
  await page.goto('/quotes');
  await page.getByRole('link', { name: reference }).first().click();
  await page.waitForURL(/\/quotes\/[0-9a-f-]+$/);
}

export async function sendQuote(page: Page) {
  await page.getByRole('button', { name: /send to customer/i }).click();
  await page.getByRole('button', { name: /approve quote/i }).waitFor();
}

export async function approveQuote(page: Page) {
  await page.getByRole('button', { name: /approve quote/i }).click();
  await page.getByRole('button', { name: /convert to invoice/i }).waitFor();
}

export async function convertQuoteToInvoice(page: Page) {
  await page.getByRole('button', { name: /convert to invoice/i }).click();
  await page.waitForURL(/\/invoices\/[0-9a-f-]+$/);
}

export async function createJob(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `JOB-${testId}`;

  await page.goto('/jobs');
  await page.getByRole('button', { name: /new job/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create job/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.getByPlaceholder(/service type/i).fill('Consumer unit replacement');
  await modal.locator('input[type="date"]').fill(new Date().toISOString().split('T')[0]);
  await modal.getByPlaceholder(/property address/i).fill('1 Test Road, TE1 1ST');
  await modal.getByPlaceholder(/value/i).fill('500');
  await modal.getByPlaceholder(/description/i).fill('Scheduled installation work');

  await page.getByRole('button', { name: /create job/i }).click();
  await jobCardInColumn(page, reference, 'Scheduled').waitFor();

  return reference;
}

function jobCardInColumn(page: Page, reference: string, column: string) {
  return page
    .locator('div.rounded-xl.border', { has: page.locator('span', { hasText: new RegExp(`^${column}$`) }) })
    .locator('div.rounded-lg', { hasText: reference })
    .first();
}

export async function startJobFromBoard(page: Page, reference: string) {
  await page.goto('/jobs');
  const card = jobCardInColumn(page, reference, 'Scheduled');
  await card.getByRole('button', { name: /start/i }).click();
  await jobCardInColumn(page, reference, 'In Progress').waitFor();
}

export async function completeJobFromBoard(page: Page, reference: string) {
  await page.goto('/jobs');
  const card = jobCardInColumn(page, reference, 'In Progress');
  await card.getByRole('button', { name: /complete/i }).click();
  await jobCardInColumn(page, reference, 'Completed').waitFor();
}

export async function createInvoice(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `INV-${testId}`;
  const today = new Date().toISOString().split('T')[0];
  const dueDate = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  await page.goto('/invoices');
  await page.getByRole('button', { name: /create invoice/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create invoice/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.locator('input[type="date"]').first().fill(today);
  await modal.locator('input[type="date"]').nth(1).fill(dueDate);
  await modal.getByPlaceholder(/description/i).fill('Labour and materials');
  await modal.locator('input[type="number"]').nth(1).fill('300');

  await modal.getByRole('button', { name: /create invoice/i }).click();
  await page.getByRole('link', { name: reference }).first().waitFor();

  return reference;
}

export async function openInvoiceDetail(page: Page, reference: string) {
  await page.goto('/invoices');
  await page.getByRole('link', { name: reference }).first().click();
  await page.waitForURL(/\/invoices\/[0-9a-f-]+$/);
}

export async function sendInvoice(page: Page) {
  await page.getByRole('button', { name: /send reminder/i }).click();
  await expectStatusPill(page, /sent/i);
}

export async function markInvoicePaid(page: Page) {
  await page.getByRole('button', { name: /mark as paid/i }).click();
  await expectStatusPill(page, /paid/i);
}

async function expectStatusPill(page: Page, pattern: RegExp) {
  await page.locator('span', { hasText: pattern }).filter({ hasClass: /rounded-full/ }).first().waitFor();
}
