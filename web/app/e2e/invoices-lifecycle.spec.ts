import { test, expect } from './fixtures';
import { createCustomer, createInvoice, openInvoiceDetail, sendInvoice, markInvoicePaid } from './helpers';

test('create, send and mark an invoice as paid', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);
  const reference = await createInvoice(page, customerName, testId);

  await openInvoiceDetail(page, reference);
  await expect(page.getByRole('heading', { name: /invoice detail/i })).toBeVisible();
  await expect(page.getByText(customerName)).toBeVisible();

  await sendInvoice(page);
  await expect(page.getByText(/sent/i)).toBeVisible();

  await markInvoicePaid(page);
  await expect(page.getByText(/paid/i)).toBeVisible();
});
