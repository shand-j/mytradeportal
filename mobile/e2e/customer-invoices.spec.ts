import { test } from "@playwright/test";
import {
  api,
  apiRaw,
  createTestTenant,
  expect,
  loginAsCustomer,
  loginCustomer,
  seedCustomer,
  seedLead,
  seedSentQuote,
  tap,
  Tenant,
  waitText,
} from "./helpers";

// Customer invoices in the app (G26): the customer invoice list + detail
// screens render total/status/line items, and the pay entry point is gated
// on the tenant actually taking card payments (Stripe-connected). The Pay
// action renders only when the invoice carries a payment_url, and
// POST /customer/invoices/{id}/pay mints the Stripe /pay link.

const CUSTOMER_PASSWORD = "E2E-Customer-1";

test.describe.serial("U — Customer invoices", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let invoice: { id: string; total: string; line_items: Array<{ description: string }> };

  test.beforeAll(async () => {
    tenant = await createTestTenant("cust-invoices");
    customer = { email: "invoices-customer@e2e.example.com", fullName: "E2E Invoices Customer" };
    const lead = await seedLead(tenant, {
      title: "E2E Invoices lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900555",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registration = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900555",
      quoteRequestId: lead.id,
    });
    const quote = await seedSentQuote(tenant, {
      title: "E2E Invoices quote",
      contactId: registration.customer.contact_id,
      quoteRequestId: lead.id,
      lineItems: [{ description: "Consumer unit replacement", quantity: 1, unit_price: 500 }],
    });
    // 1 × £500 + 20% VAT = £600.00.
    const created = await api(tenant, "/invoices", {
      method: "POST",
      body: { contact_id: registration.customer.contact_id, quote_id: quote.id },
    });
    await api(tenant, `/invoices/${created.id}/send`, { method: "POST" });
    invoice = created;
  });

  test("G26: the customer invoice list renders total and status", async ({ page }) => {
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "tab-invoices");
    await page.locator('[data-testid="invoice-list"]').waitFor({ state: "visible", timeout: 30000 });

    const row = page.locator(`[data-testid="invoice-${invoice.id}"]`);
    await row.waitFor({ state: "visible", timeout: 30000 });
    await expect(row).toContainText("£600");
    await expect(row).toContainText("AWAITING PAYMENT");
  });

  test("G26: the invoice detail renders line items, totals and status", async ({ page }) => {
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "tab-invoices");
    await tap(page, `invoice-${invoice.id}`);

    await expect(page.locator('[data-testid="invoice-total"]')).toContainText("£600", {
      timeout: 30000,
    });
    await expect(page.locator("body")).toContainText("Consumer unit replacement");
    await expect(page.locator("body")).toContainText("Subtotal");
    await expect(page.locator("body")).toContainText("VAT (20%)");
    await expect(page.locator("body")).toContainText("AWAITING PAYMENT");
  });

  test("G26: the pay entry point only appears when the tenant takes card payments", async ({
    page,
  }) => {
    // CustomerInvoiceDetailScreen renders "Pay now" only when the invoice
    // carries a payment_url (Stripe configured + charges enabled). This
    // tenant has no Stripe account, so no pay CTA should render at all.
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "tab-invoices");
    await tap(page, `invoice-${invoice.id}`);
    await expect(page.locator('[data-testid="invoice-pay"]')).toHaveCount(0);
  });

  test("G26: the pay endpoint contract matches the UI gating", async () => {
    const auth = await loginCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    const customerApi = { ...tenant, token: (auth.accessToken ?? auth.access_token) as string };
    const probe = await api(customerApi, `/customer/invoices/${invoice.id}`, {});

    if (probe.payment_url) {
      // Stripe configured + charges enabled: the endpoint mints a /pay link.
      const resp = await apiRaw(customerApi, `/customer/invoices/${invoice.id}/pay`, {
        method: "POST",
      });
      expect(resp.status).toBe(200);
      expect(resp.json.payment_url).toContain("/pay/");
    } else {
      // No card payments: no CTA renders, and the endpoint backs that up.
      const resp = await apiRaw(customerApi, `/customer/invoices/${invoice.id}/pay`, {
        method: "POST",
      });
      expect(resp.status).toBe(409);
    }
  });
});
