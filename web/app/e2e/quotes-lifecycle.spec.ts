import type { Route } from '@playwright/test';
import { test, expect } from './fixtures';
import {
  ensureDefaultAdminSession,
  createCustomer,
  createQuote,
  openQuoteDetail,
  sendQuote,
  approveQuote,
  convertQuoteToInvoice,
} from './helpers';

test.setTimeout(90_000);

test('create, send, approve and convert a quote', async ({ page, testId }) => {
  await ensureDefaultAdminSession(page);

  const customerName = await createCustomer(page, testId);
  const reference = await createQuote(page, customerName, testId);

  await openQuoteDetail(page, reference);
  await expect(page.getByText(customerName)).toBeVisible();

  const [quoteDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /download pdf/i }).click(),
  ]);
  expect(await quoteDownload.path()).toBeTruthy();

  const failQuotePdfRoute = (route: Route) => route.fulfill({ status: 500, body: 'pdf failed' });
  await page.route(/\/quotes\/[^/]+\/pdf$/, failQuotePdfRoute);
  await page.getByRole('button', { name: /download pdf/i }).click();
  await expect(page.getByText(/failed to download pdf \(http 500\)/i)).toBeVisible();
  await page.unroute(/\/quotes\/[^/]+\/pdf$/, failQuotePdfRoute);

  await sendQuote(page);
  await expect(page.locator('span', { hasText: /sent/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();

  await approveQuote(page);
  await expect(page.locator('span', { hasText: /accepted/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();

  await convertQuoteToInvoice(page);
  await expect(page).toHaveURL(/\/invoices\/[0-9a-f-]+$/);
  await expect(page.locator('span', { hasText: /draft/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();
});
