import type { Route } from '@playwright/test';
import { test, expect } from './fixtures';
import { createCustomer, createInvoice, openInvoiceDetail, sendInvoice, markInvoicePaid } from './helpers';

test('create, send and mark an invoice as paid', async ({ page, testId }) => {
  const customerName = await createCustomer(page, testId);
  const reference = await createInvoice(page, customerName, testId);

  await openInvoiceDetail(page, reference);
  await expect(page.getByText(customerName)).toBeVisible();

  const [invoiceDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: /download pdf/i }).click(),
  ]);
  expect(await invoiceDownload.path()).toBeTruthy();

  const failInvoicePdfRoute = (route: Route) => route.fulfill({ status: 500, body: 'pdf failed' });
  await page.route(/\/invoices\/[^/]+\/pdf$/, failInvoicePdfRoute);
  await page.getByRole('button', { name: /download pdf/i }).click();
  await expect(page.getByText(/failed to download pdf \(http 500\)/i)).toBeVisible();
  await page.unroute(/\/invoices\/[^/]+\/pdf$/, failInvoicePdfRoute);

  await sendInvoice(page);
  await expect(page.getByText(/sent/i)).toBeVisible();

  await markInvoicePaid(page);
  await expect(page.getByText('paid', { exact: true })).toBeVisible();
});
