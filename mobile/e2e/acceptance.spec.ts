import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  loginAsCustomer,
  loginAsTradeOwner,
  seedCustomer,
  seedLead,
  seedSentQuote,
  tap,
  Tenant,
  waitText,
} from "./helpers";

// Quote acceptance reconfirmation (G28, P1): when the customer's quote
// request carried preferred visit dates, accepting the quote in the app is a
// two-step reconfirmation — the customer sees the acknowledgement that the
// electrician will try to accommodate the dates, may toggle them, and the
// confirmed set is persisted on the quote. From there it surfaces to the
// electrician: the staff notification quotes the dates, the quote screen
// shows a "Customer's confirmed dates" panel, and converting to a job both
// prefills the earliest confirmed date and carries the dates into the job
// notes. The no-dates branch accepts directly with no reconfirmation panel.

const CUSTOMER_PASSWORD = "E2E-Customer-1";

const pad = (n: number) => String(n).padStart(2, "0");
const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
/** Next date whose weekday (Mon=1 … Sun=0) matches, strictly after today. */
function nextWeekday(weekday: number): Date {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  while (d.getDay() !== weekday) d.setDate(d.getDate() + 1);
  return d;
}

type Quote = {
  id: string;
  title: string;
  status: string;
  accepted_dates: string[];
};

test.describe.serial("S — Acceptance date reconfirmation", () => {
  let tenant: Tenant;
  let quoteId: string;
  let quoteTitle: string;
  let dateA: string;
  let dateB: string;
  // Second customer + quote without preferred dates — the direct-accept branch.
  let plainQuoteId: string;
  const customerA = {
    email: `accept-a-${Date.now()}@e2e.example.com`,
    fullName: "E2E Acceptance Customer A",
  };
  const customerB = {
    email: `accept-b-${Date.now()}@e2e.example.com`,
    fullName: "E2E Acceptance Customer B",
  };

  test.beforeAll(async () => {
    tenant = await createTestTenant("accept");

    // Two consecutive working days, starting next Monday.
    dateA = isoDay(nextWeekday(1));
    dateB = isoDay(new Date(new Date(`${dateA}T12:00:00`).getTime() + 86_400_000));

    // Lead WITH preferred dates → the reconfirm panel must appear.
    const leadA = await seedLead(tenant, {
      title: "E2E Full rewire preferred dates",
      category: "other",
      contact: {
        name: customerA.fullName,
        email: customerA.email,
        phone: "07700 900301",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
      preferredDates: [dateA, dateB],
    });
    const registrationA = await seedCustomer(tenant, {
      email: customerA.email,
      password: CUSTOMER_PASSWORD,
      fullName: customerA.fullName,
      phone: "07700 900301",
      quoteRequestId: leadA.id,
    });
    const quoteA = await seedSentQuote(tenant, {
      title: "E2E Full rewire quote",
      contactId: registrationA.customer.contact_id as string,
      quoteRequestId: leadA.id,
      lineItems: [{ description: "Full rewire labour", quantity: 1, unit_price: 2400 }],
    });
    quoteId = quoteA.id as string;
    quoteTitle = quoteA.title as string;

    // Lead WITHOUT preferred dates → direct accept, no panel.
    const leadB = await seedLead(tenant, {
      title: "E2E Socket run no dates",
      category: "socket_upgrade",
      contact: {
        name: customerB.fullName,
        email: customerB.email,
        phone: "07700 900302",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registrationB = await seedCustomer(tenant, {
      email: customerB.email,
      password: CUSTOMER_PASSWORD,
      fullName: customerB.fullName,
      phone: "07700 900302",
      quoteRequestId: leadB.id,
    });
    const quoteB = await seedSentQuote(tenant, {
      title: "E2E Socket run quote",
      contactId: registrationB.customer.contact_id as string,
      quoteRequestId: leadB.id,
      lineItems: [{ description: "Socket run labour", quantity: 1, unit_price: 320 }],
    });
    plainQuoteId = quoteB.id as string;
  });

  test("G28: accepting reconfirms preferred dates with the accommodation acknowledgement", async ({
    page,
  }) => {
    await loginAsCustomer(page, tenant, { email: customerA.email, password: CUSTOMER_PASSWORD });

    await tap(page, `quote-card-${quoteId}`);
    await waitText(page, quoteTitle);

    // First tap arms the reconfirmation step rather than accepting outright.
    await tap(page, "quote-accept");
    const panel = page.locator('[data-testid="quote-reconfirm-dates"]');
    await expect(panel).toBeVisible({ timeout: 30_000 });
    await expect(panel).toContainText("the electrician will try to accommodate them");
    await expect(panel).toContainText(dateA);
    await expect(panel).toContainText(dateB);

    // Toggling a date off and back on keeps it in the confirmed set.
    await tap(page, "reconfirm-date-1");
    await tap(page, "reconfirm-date-1");

    await tap(page, "quote-confirm-accept");

    // The acknowledgement is the acceptance confirmation shown afterwards.
    await waitText(page, "try to accommodate your preferred dates", 30_000);

    // The reconfirmed dates persist on the quote server-side.
    const quote = (await api(tenant, `/quotes/${quoteId}`)) as Quote;
    expect(quote.status).toBe("approved");
    expect(quote.accepted_dates).toEqual([dateA, dateB]);
  });

  test("G28: the staff notification quotes the reconfirmed dates", async () => {
    const notifications = (await api(tenant, "/notifications")) as Array<{
      type: string;
      body: string;
    }>;
    const accepted = notifications.find((n) => n.type === "quote_accepted");
    expect(accepted, "no quote_accepted staff notification").toBeTruthy();
    expect(accepted!.body).toContain("Customer confirmed preferred dates");
    expect(accepted!.body).toContain(dateA);
    expect(accepted!.body).toContain(dateB);
  });

  test("G28: the electrician sees the confirmed dates on the quote", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/quote/${quoteId}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote");

    const panel = page.locator('[data-testid="quote-accepted-dates"]');
    await expect(panel).toBeVisible({ timeout: 30_000 });
    await expect(panel).toContainText("Customer's confirmed dates");
    await expect(panel).toContainText(dateA);
    await expect(panel).toContainText(dateB);
  });

  test("G28: converting to a job prefills the earliest date and carries the dates into the job", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/quote/${quoteId}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote");

    await tap(page, "quote-more-actions");
    await tap(page, "quote-convert-job");
    await waitText(page, "Job detail", 30_000);

    const jobs = (await api(tenant, "/jobs")) as Array<{
      id: string;
      quote_id: string;
      scheduled_start: string | null;
      notes: string | null;
    }>;
    const job = jobs.find((j) => j.quote_id === quoteId);
    expect(job, "quote did not convert to a job").toBeTruthy();

    // No explicit slot was given: the earliest confirmed date prefills 09:00
    // (naive-local schedule convention).
    expect(job!.scheduled_start).toBe(`${dateA}T09:00:00`);
    // The reconfirmed dates ride into the job notes for the on-site visit.
    expect(job!.notes).toContain("Customer confirmed preferred dates");
    expect(job!.notes).toContain(dateA);
    expect(job!.notes).toContain(dateB);
  });

  test("G28: a quote without preferred dates accepts directly with no reconfirmation panel", async ({
    page,
  }) => {
    await loginAsCustomer(page, tenant, { email: customerB.email, password: CUSTOMER_PASSWORD });

    await tap(page, `quote-card-${plainQuoteId}`);
    await waitText(page, "E2E Socket run quote");

    // The reconfirmation panel is gated on the request carrying dates.
    await expect(
      page.locator('[data-testid="quote-reconfirm-dates"]')
    ).toHaveCount(0);
    // Accept goes straight through — no Confirm step is offered.
    await expect(page.locator('[data-testid="quote-confirm-accept"]')).toHaveCount(0);

    await tap(page, "quote-accept");
    await waitText(page, "try to accommodate your preferred dates", 30_000);

    const quote = (await api(tenant, `/quotes/${plainQuoteId}`)) as Quote;
    expect(quote.status).toBe("approved");
    expect(quote.accepted_dates).toEqual([]);
  });
});
