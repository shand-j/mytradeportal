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

  await sendQuote(page);
  await expect(page.locator('span', { hasText: /sent/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();

  await approveQuote(page);
  await expect(page.locator('span', { hasText: /accepted/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();

  await convertQuoteToInvoice(page);
  await expect(page).toHaveURL(/\/invoices\/[0-9a-f-]+$/);
  await expect(page.locator('span', { hasText: /draft/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();
});
