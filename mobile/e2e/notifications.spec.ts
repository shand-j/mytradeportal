import { test } from "@playwright/test";
import {
  api,
  bodyText,
  createTestTenant,
  expect,
  loginAsCustomer,
  loginAsTradeOwner,
  seedCustomer,
  seedLead,
  seedScheduledJob,
  seedSentQuote,
  sleep,
  tap,
  Tenant,
  waitText,
} from "./helpers";

const CUSTOMER_PASSWORD = "E2E-Customer-1";

// Bell-list deep links: a mapped notification lands on its entity screen; an
// unmapped one (customer invoice links have no customer route) marks read and
// stays put without erroring. Both notifications are produced by API-side
// effects — no LLM involvement.

test.describe.serial("O — Notifications", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let job: { id: string; title: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("notifications");
    customer = { email: "notif-customer@e2e.example.com", fullName: "E2E Notif Customer" };

    // Scheduling a job fires a staff "job_scheduled" notification (/job/{id}).
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const scheduledStart = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00:00`;
    job = await seedScheduledJob(tenant, {
      title: "E2E Notified job",
      scheduledStart,
    });

    // Sending an invoice linked to a registered customer's quote fires a
    // customer "invoice_sent" notification (/customer/invoice/{id}), which the
    // customer app intentionally does not route anywhere.
    const lead = await seedLead(tenant, {
      title: "E2E Notified lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900777",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registration = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900777",
      quoteRequestId: lead.id,
    });
    const quote = await seedSentQuote(tenant, {
      title: "E2E Notified quote",
      contactId: registration.customer.contact_id,
      quoteRequestId: lead.id,
    });
    const invoice = await api(tenant, "/invoices", {
      method: "POST",
      body: {
        contact_id: registration.customer.contact_id,
        quote_id: quote.id,
        line_items: [{ description: "E2E notified invoice line", quantity: 1, unit_price: 120 }],
        vat_rate: 0.2,
      },
    });
    await api(tenant, `/invoices/${invoice.id}/send`, { method: "POST" });
  });

  test("N2: tapping the job notification deep-links to the job detail", async ({ page }) => {
    const notifications = (await api(tenant, "/notifications")) as Array<{
      id: string;
      type: string;
      link: string | null;
    }>;
    const jobNotification = notifications.find((n) => n.link === `/job/${job.id}`);
    expect(jobNotification, "no staff notification for the scheduled job").toBeTruthy();

    await loginAsTradeOwner(page, tenant);
    await tap(page, "notifications-bell-trade");
    await waitText(page, "Notifications");

    await tap(page, `notification-${jobNotification!.id}`);
    await waitText(page, "Job detail", 30000);
    await waitText(page, job.title);
  });

  test("N2: an unmapped customer notification navigates nowhere without error", async ({
    page,
  }) => {
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "notifications-bell-customer");
    await waitText(page, "Notifications");

    const row = page
      .locator('[data-testid^="notification-"]', { hasText: "Invoice ready" })
      .first();
    await row.waitFor({ state: "visible", timeout: 30000 });
    await row.click({ force: true });
    await sleep(1000);

    // Customer invoice links resolve to no route: the row marks read and the
    // app stays on the notifications screen without surfacing an error.
    await waitText(page, "Notifications");
    expect(page.url()).toContain("notifications");
    const text = (await bodyText(page)).toLowerCase();
    expect(text).not.toContain("something went wrong");
    expect(text).not.toContain("could not load");
  });
});
