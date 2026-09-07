import { test } from "@playwright/test";
import {
  api,
  apiContext,
  bodyText,
  createTestTenant,
  expect,
  fill,
  loginAsCustomer,
  loginAsTradeOwner,
  seedBusinessServices,
  seedCommunication,
  seedCustomer,
  seedLead,
  seedScheduledJob,
  seedSentQuote,
  sleep,
  tap,
  tapText,
  Tenant,
  waitForInvoice,
  waitForJob,
  waitForLead,
  waitForQuote,
  waitText,
} from "./helpers";

const CUSTOMER_PASSWORD = "E2E-Customer-1";

// Config sets ``fullyParallel: true`` and ``workers > 1`` so different
// describes can run on different workers. Individual describes below use
// ``test.describe.serial`` for the ones that share ``beforeAll`` tenant
// state, so their tests stay in order within one worker.

test.describe.serial("A — Trade owner login & settings", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("trade-login");
  });

  test("trade owner logs in and sees dashboard", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await waitText(page, "Dashboard");
  });

  test("settings shows 6-digit customer code", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "dashboard-more");
    await waitText(page, "Customer code");
    const visibleCode = (await bodyText(page)).replace(/\s+/g, " ");
    expect(visibleCode).toContain(tenant.code);
  });
});

test.describe.serial("B — Customer quote request + account creation", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("customer-quote");
    await seedBusinessServices(tenant);
  });

  test("customer submits a quote request and creates an account", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await waitText(page, "My Trade Portal", 120000);

    // Look up the business by its 6-digit customer code.
    for (let i = 0; i < 6; i++) {
      await page.locator(`[data-testid="business-code-${i}"]`).fill(tenant.code[i]);
    }
    await tap(page, "entry-find-business");
    await waitText(page, "Your electrician", 30000);

    await tap(page, "entry-request-quote");

    // Postcode
    await fill(page, "quote-postcode-input", "SK8 3NJ");
    await tap(page, "quote-check-area");

    // Contact
    await fill(page, "quote-name-input", "E2E Jane Homeowner");
    await fill(page, "quote-phone-input", "07700 900123");
    await fill(page, "quote-email-input", "jane-homeowner@e2e.example.com");
    await tapText(page, "In-app Chat");
    await tap(page, "quote-contact-continue");

    // Property profile
    await tapText(page, "Detached");
    await tapText(page, "Post-2000");
    await tapText(page, "Owner");
    await tapText(page, "Yes"); // parking
    await tapText(page, "Modern RCBO");
    await tap(page, "quote-property-continue");

    // Category
    await tap(page, "quote-category-consumer_unit");
    await tap(page, "quote-category-continue");

    // Consumer-unit questionnaire
    await fill(page, "quote-cu-circuits", "8");
    await tapText(page, "Old fuse wire");
    await tapText(page, "None"); // known faults
    await tapText(page, "Yes"); // occupied
    await tap(page, "quote-consumer-unit-continue");

    // Media
    await tap(page, "quote-media-continue");

    // Urgency
    await tapText(page, "This week");
    await tap(page, "quote-urgency-continue");

    // Budget
    await tap(page, "quote-budget-continue");

    // Consents
    await tap(page, "quote-consent-terms");
    await tap(page, "quote-consent-contact");
    await tap(page, "quote-submit");

    // Confirmation + account creation
    await waitText(page, "has your request");
    await tap(page, "quote-create-account");
    await fill(page, "account-password", CUSTOMER_PASSWORD);
    await fill(page, "account-confirm-password", CUSTOMER_PASSWORD);
    await tapText(page, "Create account");

    // Account creation logs the customer in and lands them on requests.
    await waitText(page, "Request a new quote", 60000);

    const lead = await waitForLead(tenant, "Consumer unit", 30000);
    expect(lead).toBeTruthy();
  });
});

test.describe.serial("C — AI quote generation and send", () => {
  let tenant: Tenant;
  let leadId: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("ai-quote");
    await seedBusinessServices(tenant);
    const lead = await seedLead(tenant, {
      title: "E2E AI consumer unit",
      category: "consumer_unit",
      contact: {
        name: "E2E AI Lead",
        email: "ai-lead@e2e.example.com",
        phone: "07700 900321",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
      structuredData: {
        property: { type: "detached", age: "post_2000", bedrooms: 3, parking: true },
        questionnaire: { consumer_unit: { circuits: "8", reason: "old_fuse_wire" }, notes: "" },
      },
    });
    leadId = lead.id;
  });

  test.slow();
  test("trade owner generates an AI quote and sends it", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await waitText(page, "Dashboard");

    await page.goto(`/(trade)/lead/${leadId}`, { waitUntil: "networkidle" });
    await waitText(page, "Lead detail");
    await tap(page, "lead-generate-quote");

    await waitText(page, "Quote intake");
    await tap(page, "intake-property-type-house");
    await tap(page, "intake-bedrooms-3");
    await tap(page, "intake-cu-location-hallway");
    await fill(page, "intake-parking", "Driveway parking");
    await fill(page, "intake-access", "Key safe code 1234");
    await tap(page, "intake-generate-quote");

    // Poll backend until a draft quote linked to the lead exists.
    // AI generation can take well over 2 minutes with the real LLM, so poll for up to 4 minutes.
    let draft: { id: string; title: string } | undefined;
    for (let i = 0; i < 240; i++) {
      const quotes = (await api(tenant, "/quotes")) as Array<{
        id: string;
        title: string;
        status: string;
        quote_request_id: string | null;
      }>;
      draft = quotes.find((q) => q.status === "draft" && q.quote_request_id === leadId);
      if (draft) break;
      await sleep(1000);
    }
    if (!draft) {
      throw new Error("AI-generated draft quote not found for the lead");
    }

    await page.goto(`/(trade)/quote/${draft.id}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote");
    await fill(page, "quote-line-description-0", "Consumer unit replacement - upgraded scope");
    await tap(page, "quote-approve-send");

    // Poll until the quote linked to the lead is marked as sent.
    let sentQuote: { id: string; status: string } | undefined;
    for (let i = 0; i < 30; i++) {
      const quotes = (await api(tenant, "/quotes")) as Array<{
        id: string;
        status: string;
        quote_request_id: string | null;
      }>;
      sentQuote = quotes.find((q) => q.status === "sent" && q.quote_request_id === leadId);
      if (sentQuote) break;
      await sleep(1000);
    }
    if (!sentQuote) {
      throw new Error("Quote was not marked as sent");
    }
  });
});

test.describe.serial("D — Customer accept + book", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let quote: { id: string; title: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("customer-book");
    customer = { email: "d-customer@e2e.example.com", fullName: "E2E Book Customer" };
    const lead = await seedLead(tenant, {
      title: "E2E Bookable quote",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900456",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const customerResult = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900456",
      quoteRequestId: lead.id,
    });
    const quoteResult = await seedSentQuote(tenant, {
      title: "E2E Bookable quote",
      contactId: customerResult.customer.contact_id,
      quoteRequestId: lead.id,
    });
    quote = quoteResult;
  });

  test("customer accepts a sent quote and books a slot", async ({ page }) => {
    await loginAsCustomer(page, tenant, { email: customer.email, password: CUSTOMER_PASSWORD });

    await tap(page, `quote-card-${quote.id}`);
    await waitText(page, quote.title);
    await tapText(page, "Accept quote");
    await waitText(page, "Book a date");

    await tap(page, "book-day-0");
    await tap(page, "book-time-0");
    await tapText(page, "Confirm booking");

    // Should land on the customer calendar.
    await waitText(page, "Appointments");
    await waitText(page, quote.title, 60000);
  });
});

test.describe.serial("E — Trade job lifecycle + invoice", () => {
  let tenant: Tenant;
  let job: { id: string; title: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("job-lifecycle");
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const scheduledStart = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00:00`;
    const created = await seedScheduledJob(tenant, {
      title: "E2E Lifecycle job",
      scheduledStart,
    });
    job = created;
  });

  test("trade owner completes a job and raises an invoice", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await waitText(page, "Dashboard");

    await page.goto(`/(trade)/job/${job.id}`, { waitUntil: "networkidle" });
    await waitText(page, "Job detail");

    await tap(page, "job-start");
    await waitForJob(tenant, "E2E Lifecycle job", "in_progress", 30000);

    await tap(page, "job-complete");
    await waitForJob(tenant, "E2E Lifecycle job", "completed", 30000);

    await tap(page, "job-create-invoice");
    await waitText(page, "Invoice");
    await tap(page, "invoice-mark-paid");
    await waitText(page, "Payment received");

    await waitForInvoice(tenant, "E2E Lifecycle job", "paid", 30000);
  });
});

test.describe.serial("F — In-app chat", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let leadId: string;

  test.beforeAll(async () => {
    // Seeding up to 3 real-LLM follow-up turns (55-77s each) plus tenant
    // creation can exceed the default 300s hook timeout.
    test.setTimeout(600_000);
    tenant = await createTestTenant("chat");
    customer = { email: "f-customer@e2e.example.com", fullName: "E2E Chat Customer" };
    const lead = await seedLead(tenant, {
      title: "E2E Chat lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900789",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
      // Deliberately omit the number of circuits so the AI has an obvious,
      // contextual gap to ask about. The property profile is included so the
      // question can reference real details from the request.
      structuredData: {
        property: { type: "detached", age: "post_2000", bedrooms: 3, parking: true, tenure: "owner" },
        questionnaire: { consumer_unit: { reason: "old_fuse_wire", known_faults: "none", occupied: "yes" } },
        notes: "Want to upgrade to a modern RCBO board.",
      },
    });
    leadId = lead.id;
    await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900789",
      quoteRequestId: leadId,
    });
    // Seed two question turns (with interleaved customer replies). The post-reply
    // follow-up in the test is then deterministically the FINAL turn, which the
    // backend always closes — confident closure ("…notified…") or turn-cap
    // callback closure ("…give you a call…"), matching the product's dual-closure
    // design. Early high-confidence closures make extra turns no-ops.
    await seedCommunication(tenant, { quoteRequestId: leadId, turns: 2 });
  });

  // Seeding up to 3 LLM follow-ups plus the in-test follow-up can take several
  // minutes with the real model (55-77s per call).
  test.slow();
  test("customer replies to an AI assistant follow-up", async ({ page }) => {
    await loginAsCustomer(page, tenant, { email: customer.email, password: CUSTOMER_PASSWORD });

    // The AI assistant banner opens messages for the first request.
    await tap(page, "customer-ai-banner");
    // Wait for the chat screen to load with the seeded AI follow-up message.
    await page.locator('[data-testid="chat-composer"]').waitFor({ state: "visible", timeout: 30000 });

    // Verify the AI question is contextual (references circuits/fuse box) and
    // not a generic "tell us more" message.
    const pageText = (await bodyText(page)).toLowerCase();
    expect(
      pageText.includes("circuits") || pageText.includes("fuse box") || pageText.includes("fusebox"),
      `Expected a contextual AI follow-up about circuits, got: ${pageText}`
    ).toBeTruthy();

    const reply = "It has 8 circuits including the main switch.";
    await fill(page, "chat-composer", reply);
    await tap(page, "chat-send");
    await waitText(page, reply);

    // After the customer reply, the AI should close the loop with a thank-you
    // message confirming the electrician will review the request. The LLM call
    // takes 55-77s, so allow generous time for it to be generated and rendered.
    await waitText(page, "electrician", 180000);

    // Assert the backend thread contains the reply and the final AI closure.
    const messages = (await api(tenant, `/communications?quote_request_id=${leadId}`)) as Array<{
      body: string;
      sender_role: string;
      ai_metadata: { complete?: boolean; confidence?: number } | null;
    }>;
    const replyMessage = messages.find(
      (m) => m.sender_role === "customer" && m.body === reply
    );
    expect(replyMessage).toBeTruthy();

    const finalAi = messages
      .filter((m) => m.sender_role === "ai")
      .pop();
    expect(finalAi).toBeTruthy();
    // The final turn always closes: confident closure ("…notified…") or
    // turn-cap callback closure ("…give you a call…") — both are valid per the
    // product's dual-closure design; which one depends on LLM confidence.
    expect(finalAi!.body?.toLowerCase()).toMatch(/notified|give you a call/);
    expect(finalAi!.ai_metadata?.complete).toBe(true);
  });
});

test.describe.serial("G — Fresh business signup", () => {
  test("owner starts the business signup wizard from the entry screen", async ({ page }) => {
    // Full-onboarding coverage lives in a dedicated wizard suite (post-beta);
    // this smoke asserts the register-business path opens the onboarding
    // wizard rather than a broken dead-end. The wizard header shows
    // "Onboarding" until the business name is set, so we anchor on that.
    await page.goto("/", { waitUntil: "networkidle" });
    await waitText(page, "My Trade Portal", 120000);
    await tap(page, "entry-register-trade");
    await waitText(page, "Onboarding", 30000);
  });
});

test.describe.serial("H — Refine quote round-trip", () => {
  let tenant: Tenant;
  let quoteId: string;

  test.beforeAll(async () => {
    test.setTimeout(600_000);
    tenant = await createTestTenant("refine");
    const customer = { email: `refine-${Date.now()}@e2e.example.com`, fullName: "E2E Refine" };
    const lead = await seedLead(tenant, {
      title: "Refine baseline — kitchen sockets",
      category: "sockets",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900901",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
      structuredData: { notes: "Two extra doubles in the kitchen." },
    });
    // Kick off the first AI quote so we have something to refine.
    const generated = (await api(tenant, "/quotes/generate", {
      method: "POST",
      body: { quote_request_id: lead.id },
    })) as { id: string };
    quoteId = generated.id;
  });

  test.slow();
  test("owner refines an AI-drafted quote and the totals update", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/quote/${quoteId}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote", 30000);

    // Capture the baseline total from the DB then submit a refine.
    const before = (await api(tenant, `/quotes/${quoteId}`)) as { total: string };
    await fill(page, "refine-instructions", "Add a second RCBO on the new circuit for redundancy.");
    await tap(page, "refine-submit");

    // Refine calls Kimi (60-120s). Poll the API for the total to change.
    let after = before;
    const deadline = Date.now() + 240_000;
    while (Date.now() < deadline) {
      after = (await api(tenant, `/quotes/${quoteId}`)) as { total: string };
      if (after.total !== before.total) break;
      await sleep(3000);
    }
    expect(after.total, "refine did not change quote total").not.toBe(before.total);
  });
});

test.describe.serial("I — Multi-user tenant (owner + engineer)", () => {
  let tenant: Tenant;
  let engineerEmail: string;
  const engineerPassword = "EngineerBeta1!";

  test.beforeAll(async () => {
    tenant = await createTestTenant("multi-user");
    engineerEmail = `engineer-${Date.now()}@e2e.example.com`;
    // Owner is created by createTestTenant. Provision the engineer via the
    // same /users endpoint the settings page uses.
    await api(tenant, "/users", {
      method: "POST",
      body: {
        email: engineerEmail,
        password: engineerPassword,
        full_name: "E2E Engineer",
        role: "engineer",
      },
    });
  });

  test("engineer logs in and lands on the dashboard", async ({ page }) => {
    // Engineer login reuses the trade login form; only the identity differs.
    await page.goto("/", { waitUntil: "networkidle" });
    await waitText(page, "My Trade Portal", 120000);
    await tap(page, "entry-trade-login");
    await waitText(page, "Electrician login");
    await fill(page, "login-email", engineerEmail);
    await fill(page, "login-password", engineerPassword);
    await tap(page, "login-submit");
    await waitText(page, "Dashboard", 60000);
  });
});
