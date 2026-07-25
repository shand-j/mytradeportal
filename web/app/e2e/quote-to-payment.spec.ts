import { test, expect } from './fixtures';
import {
  ensureDefaultAdminSession,
  createCustomer,
  createQuote,
  openQuoteDetail,
  sendQuote,
  approveQuote,
  convertQuoteToInvoice,
  sendInvoice,
  markInvoicePaid,
} from './helpers';

test.setTimeout(90_000);

test('quote request becomes a paid invoice', async ({ page, testId }) => {
  await ensureDefaultAdminSession(page);

  const customerName = await createCustomer(page, testId);
  const reference = await createQuote(page, customerName, testId);

  await openQuoteDetail(page, reference);
  await sendQuote(page);
  await approveQuote(page);
  await convertQuoteToInvoice(page);

  await sendInvoice(page);
  await markInvoicePaid(page);

  await expect(page.locator('span', { hasText: /paid/i }).filter({ hasClass: /rounded-full/ }).first()).toBeVisible();
  await expect(page.getByText(/amount due/i)).not.toBeVisible();
});
