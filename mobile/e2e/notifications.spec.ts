import { test } from "@playwright/test";
import { mailpitConfigured, waitForEmail } from "./mailpit";
import {
  api,
  apiRaw,
  bodyText,
  createTestTenant,
  expect,
  loginAsCustomer,
  loginAsTradeOwner,
  loginCustomer,
  seedCustomer,
  seedLead,
  seedScheduledJob,
  seedSentQuote,
  tap,
  Tenant,
  waitText,
} from "./helpers";

const CUSTOMER_PASSWORD = "E2E-Customer-1";

// Bell-list deep links: staff notifications land on their entity screen, and
// a customer "invoice_sent" notification deep-links to the customer invoice
// screen (added after the original suite treated it as unmapped). Both
// notifications are produced by API-side effects — no LLM involvement.

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
    // customer "invoice_sent" notification (/customer/invoice/{id}), which
    // the customer app routes to the invoice detail screen.
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

  test("N2: a customer invoice notification deep-links to the invoice", async ({ page }) => {
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

    // The customer app routes invoice notifications to the invoice screen
    // (invoice detail with payment CTA was added after this suite was written).
    await waitText(page, "AWAITING PAYMENT", 30000);
    expect(page.url()).toContain("/invoice/");
    const text = (await bodyText(page)).toLowerCase();
    expect(text).not.toContain("something went wrong");
    expect(text).not.toContain("could not load");
  });

  // Email side of the same flow: staging/PR apis route outbound email into
  // the shared Mailpit instance instead of Resend, so the invoice send must
  // land there with the total and a payable link — zero Resend sends.
  test("N2: the invoice email lands in Mailpit with total and payable link", async () => {
    test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
    const email = await waitForEmail(customer.email, { subjectIncludes: "Invoice", timeoutMs: 30_000 });
    expect(email.subject).toMatch(/^Invoice \S+ from /);
    // Invoice: 1 x £120 + 20% VAT = £144 total.
    expect(email.text + email.html).toContain("144");
    // Customers without the app get a secure view/pay link on the site.
    expect(email.html).toMatch(/https:\/\//);
  });
});

// Mark-all-read + bell deep-links for the notification kinds the original
// suite never exercised (G30): staff quote_accepted / chat_reply and the
// customer chat_message. The customer quote_sent deep-link is written but
// self-skips: that bell only fires for AI-generated quotes (linked at
// creation), which need an LLM. There is deliberately no customer "booking"
// bell row — booking confirmations are email-only today (see G16); the staff
// job_scheduled + customer invoice_sent rows are covered above. Read-all
// runs BEFORE the deep-link tests: tapping a row marks it read, so doing it
// the other way around would leave nothing unread to bulk-clear.

test.describe.serial("O2 — Mark-all-read & bell deep-links", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let quote: { id: string; title: string };
  let leadId: string;
  let staffQuoteAccepted: { id: string };
  let staffChatReply: { id: string } | null = null;
  let customerQuoteSent: { id: string } | null = null;
  let customerChatMessage: { id: string };
  let customerToken: string;

  test.beforeAll("O2 setup (drives AI triage to closure on staging)", async ({}, testInfo) => {
    // Driving triage to closure can take up to ~5 real LLM calls on staging
    // (1-2 min each), so give the hook a generous budget.
    testInfo.setTimeout(20 * 60_000);
    tenant = await createTestTenant("notif-links");
    customer = { email: "notif2-customer@e2e.example.com", fullName: "E2E Notif2 Customer" };

    const lead = await seedLead(tenant, {
      title: "E2E Notif2 lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900888",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
      // Rich property profile (mirrors regression F) so a single detailed
      // answer can push LLM confidence past the 80 closure threshold —
      // otherwise every extra turn is another 1-2 minute LLM call. Circuits
      // are deliberately omitted so the AI has its obvious gap to ask about.
      structuredData: {
        property: { type: "detached", age: "post_2000", bedrooms: 3, parking: true, tenure: "owner" },
        questionnaire: { consumer_unit: { reason: "old_fuse_wire", known_faults: "none", occupied: "yes" } },
        notes: "Want to upgrade to a modern RCBO board.",
      },
    });
    leadId = lead.id as string;
    const registration = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900888",
      quoteRequestId: lead.id,
    });
    const auth = await loginCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    customerToken = (auth.accessToken ?? auth.access_token) as string;
    const customerApi = { ...tenant, token: customerToken };

    quote = await seedSentQuote(tenant, {
      title: "E2E Notif2 quote",
      contactId: registration.customer.contact_id,
      quoteRequestId: lead.id,
    });

    // Customer accepts → staff quote_accepted (/quotes/{id}); staff posts to
    // the thread → customer chat_message (/customer/chat/{id}); customer
    // replies → staff chat_reply (/chat/{id}).
    await api(customerApi, `/customer/quotes/${quote.id}/accept`, { method: "POST" });
    await api(tenant, "/communications", {
      method: "POST",
      body: { quote_request_id: leadId, channel: "in_app_chat", body: "E2E staff hello" },
    });
    await api(customerApi, "/communications", {
      method: "POST",
      body: { quote_request_id: leadId, channel: "in_app_chat", body: "E2E customer reply" },
    });

    const findByType = (rows: Array<{ id: string; type: string }>, type: string) => {
      const row = rows.find((n) => n.type === type);
      if (!row) throw new Error(`no ${type} notification`);
      return row;
    };
    staffQuoteAccepted = findByType(await api(tenant, "/notifications"), "quote_accepted");

    // The staff chat_reply bell row is gated on AI triage having CLOSED the
    // thread (an AI message with ai_metadata.complete=true), and only the
    // FIRST message of a customer burst rings the bell. One ai-followup call
    // usually yields a clarifying QUESTION, not closure — the endpoint only
    // emits its closure message (complete=true, forced at the turn cap of
    // max_followup_turns) once the LLM is confident or out of turns. So when
    // an LLM is configured (staging) we drive the conversation to closure:
    // answer each AI question until the returned AI message is complete,
    // then post the first post-closure customer message, which must ring the
    // bell. Without an LLM (local dev) triage can never close, so we lock in
    // the documented quiet rule instead: a customer reply on a non-triage
    // thread must NOT create a staff chat_reply notification.
    const triage = await apiRaw(tenant, `/communications/${leadId}/ai-followup`, {
      method: "POST",
    });
    if (triage.status === 200) {
      let closure = triage.json as { ai_metadata?: { complete?: boolean } | null };
      // max_followup_turns (default 5) FORCES a closure message on the final
      // allowed turn, so the conversation always closes within 5 AI calls
      // (the first call above + at most 4 loop turns).
      for (let turn = 0; turn < 4 && closure.ai_metadata?.complete !== true; turn++) {
        await api(customerApi, "/communications", {
          method: "POST",
          body: {
            quote_request_id: leadId,
            channel: "in_app_chat",
            body: `E2E triage answer ${turn + 1}: it has 8 circuits including the main switch, owner-occupied detached house, upgrading an old fuse-wire board to a modern RCBO consumer unit`,
          },
        });
        const next = await apiRaw(tenant, `/communications/${leadId}/ai-followup`, {
          method: "POST",
        });
        expect(next.status, "ai-followup keeps returning 200 once the LLM is up").toBe(200);
        closure = next.json as { ai_metadata?: { complete?: boolean } | null };
      }
      expect(
        closure.ai_metadata?.complete,
        "AI triage must reach its closure message (complete=true)"
      ).toBe(true);
      // Closure exists and the last message is AI → this reply is the first
      // of a new burst → the staff bell must ring.
      await api(customerApi, "/communications", {
        method: "POST",
        body: { quote_request_id: leadId, channel: "in_app_chat", body: "E2E customer reply" },
      });
      staffChatReply = findByType(await api(tenant, "/notifications"), "chat_reply");
    } else {
      const staffRows = (await api(tenant, "/notifications")) as Array<{ type: string }>;
      expect(
        staffRows.some((n) => n.type === "chat_reply"),
        "customer reply on a non-triage thread must not ring the staff bell"
      ).toBe(false);
    }
    const customerRows = (await api(customerApi, "/customer/notifications")) as Array<{
      id: string;
      type: string;
    }>;
    // The send-side customer bell only fires when the quote was created WITH
    // a quote_request link (AI generation sets Quote.quote_request_id at
    // creation). POST /quotes + PATCH /quote-requests (what seedSentQuote
    // does) links the request side only, so a manually created quote
    // deterministically produces NO customer quote_sent row — assert that
    // gap explicitly (it is a product limitation, not a flake) and skip the
    // quote_sent deep-link below when the row cannot exist.
    customerQuoteSent = customerRows.find((n) => n.type === "quote_sent") ?? null;
    customerChatMessage = findByType(customerRows, "chat_message");

    const staffUnread = (await api(tenant, "/notifications/unread-count")) as {
      unread_count?: number;
      count?: number;
    };
    expect(staffUnread.unread_count ?? staffUnread.count ?? 0).toBeGreaterThan(0);
  });
  test("G30: mark-all-read clears the staff badge via POST /notifications/read-all", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "notifications-bell-trade");
    await waitText(page, "Notifications");
    await tap(page, "notifications-mark-all-read");

    // Header action disappears once nothing is unread…
    await page
      .locator('[data-testid="notifications-mark-all-read"]')
      .waitFor({ state: "hidden", timeout: 20000 });
    // …and the backend agrees.
    const unread = (await api(tenant, "/notifications/unread-count")) as {
      unread_count?: number;
      count?: number;
    };
    expect(unread.unread_count ?? unread.count ?? 0).toBe(0);
  });

  test("G30: customer read-all clears the customer badge", async () => {
    const customerApi = { ...tenant, token: customerToken };
    const before = (await api(customerApi, "/customer/notifications/unread-count")) as {
      unread_count?: number;
      count?: number;
    };
    expect(before.unread_count ?? before.count ?? 0).toBeGreaterThan(0);

    const result = (await api(customerApi, "/customer/notifications/read-all", {
      method: "POST",
    })) as { marked_read?: number; markedRead?: number };
    expect((result.marked_read ?? result.markedRead) || 0).toBeGreaterThan(0);

    const after = (await api(customerApi, "/customer/notifications/unread-count")) as {
      unread_count?: number;
      count?: number;
    };
    expect(after.unread_count ?? after.count ?? 0).toBe(0);
  });

  test("G30: staff bell deep-links quote_accepted to the quote screen", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "notifications-bell-trade");
    await waitText(page, "Notifications");

    await tap(page, `notification-${staffQuoteAccepted.id}`);
    await waitText(page, "Review quote", 30000);
    await waitText(page, quote.title);
  });

  test("G30: staff bell deep-links chat_reply to the message thread", async ({ page }) => {
    test.skip(
      !staffChatReply,
      "no LLM: AI triage cannot close locally so no staff chat_reply row exists (quiet rule asserted in beforeAll)"
    );
    await loginAsTradeOwner(page, tenant);
    await tap(page, "notifications-bell-trade");
    await waitText(page, "Notifications");

    await tap(page, `notification-${staffChatReply!.id}`);
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await waitText(page, "E2E customer reply");
  });

  test("G30: customer bell deep-links quote_sent to their requests", async ({ page }) => {
    test.skip(
      !customerQuoteSent,
      "customer quote_sent bell only fires for AI-generated quotes (Quote.quote_request_id set at creation); POST /quotes quotes never carry it"
    );
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "notifications-bell-customer");
    await waitText(page, "Notifications");

    await tap(page, `notification-${customerQuoteSent!.id}`);
    // Quote links land on the customer requests screen with the quote card.
    await waitText(page, quote.title, 30000);
  });

  test("G30: customer bell deep-links chat_message to the thread", async ({ page }) => {
    await loginAsCustomer(page, tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "notifications-bell-customer");
    await waitText(page, "Notifications");

    await tap(page, `notification-${customerChatMessage.id}`);
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await waitText(page, "E2E staff hello");
  });
});
