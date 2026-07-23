import { test, expect } from './fixtures';
import { createCustomer, createQuote, openQuoteDetail, sendQuote, approveQuote, convertQuoteToInvoice } from './helpers';

test('create, send, approve and convert a quote', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);
  const reference = await createQuote(page, customerName, testId);

  await openQuoteDetail(page, reference);
  await expect(page.getByText(customerName)).toBeVisible();

  await sendQuote(page);
  await expect(page.getByText('sent', { exact: true })).toBeVisible();

  await approveQuote(page);
  await expect(page.getByText('accepted', { exact: true })).toBeVisible();

  await convertQuoteToInvoice(page);
  await expect(page).toHaveURL(/\/invoices\/[0-9a-f-]+$/);
  await expect(page.getByText('draft', { exact: true })).toBeVisible();
});
