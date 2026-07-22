import { test, expect } from './fixtures';
import {
  createCustomer,
  createQuote,
  openQuoteDetail,
  sendQuote,
  approveQuote,
  convertQuoteToInvoice,
  sendInvoice,
  markInvoicePaid,
} from './helpers';

test('quote request becomes a paid invoice', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);
  const reference = await createQuote(page, customerName, testId);

  await openQuoteDetail(page, reference);
  await sendQuote(page);
  await approveQuote(page);
  await convertQuoteToInvoice(page);

  await sendInvoice(page);
  await markInvoicePaid(page);

  await expect(page.getByText(/paid/i)).toBeVisible();
  await expect(page.getByText(/amount due/i)).not.toBeVisible();
});
