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

// Node's global Buffer exists at runtime under Playwright, but the app
// tsconfig doesn't include node types — declare the single use here.
declare const Buffer: { from(data: string, encoding: "base64"): any };

// 1x1 transparent PNG — the smallest valid upload for the photo flows.
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
);

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
  const JANE_EMAIL = "jane-homeowner@e2e.example.com";
  let tenant: Tenant;
  let leadId: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("customer-quote");
    await seedBusinessServices(tenant);
  });

  test("customer submits a quote request and creates an account", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    // The app opens on a splash → role-select sequence; pick the customer role.
    await page
      .locator('[data-testid="role-select"]')
      .waitFor({ state: "visible", timeout: 120000 });
    await tap(page, "role-customer");

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
    await fill(page, "quote-email-input", JANE_EMAIL);
    await tapText(page, "Online chat");
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

    const lead = (await waitForLead(tenant, "Consumer unit", 30000)) as { id: string };
    expect(lead).toBeTruthy();
    leadId = lead.id;
  });

  test("customer logs back in without the electrician code (C12)", async ({ page }) => {
    // Log in via the business code first so there is a session to log out of.
    await loginAsCustomer(page, tenant, { email: JANE_EMAIL, password: CUSTOMER_PASSWORD });
    await tap(page, "tab-profile");
    // The profile screen loads customer data from the deployed API; under CI
    // runner load (video recording + parallel workers) the render can exceed
    // tapText's default 20s, so wait generously for the logout row.
    const logout = page.getByText("Log out", { exact: false }).first();
    await logout.waitFor({ state: "visible", timeout: 60_000 });
    await logout.click({ force: true });
    await sleep(400);

    // Back on the role select: go straight to customer login — no business
    // code. Login is tenant-agnostic (the account is located by email).
    await page
      .locator('[data-testid="role-select"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await tap(page, "role-customer");
    await tap(page, "entry-customer-login");
    await waitText(page, "Customer login");
    await fill(page, "login-email", JANE_EMAIL);
    await fill(page, "login-password", CUSTOMER_PASSWORD);
    await tap(page, "login-submit");

    // Lands in the portal with the earlier request listed.
    await page
      .locator('[data-testid="request-new-quote"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await page
      .locator(`[data-testid="request-card-${leadId}"]`)
      .waitFor({ state: "visible", timeout: 30000 });
  });

  test("customer with no requests sees the welcoming empty state (C20)", async ({ page }) => {
    const email = `empty-${Date.now()}@e2e.example.com`;
    await seedCustomer(tenant, {
      email,
      password: CUSTOMER_PASSWORD,
      fullName: "E2E Empty State",
      phone: "07700 900555",
    });
    await loginAsCustomer(page, tenant, { email, password: CUSTOMER_PASSWORD });
    await waitText(page, "No requests yet");
    await waitText(page, "Tap “Request a new quote” to send your first request");
  });

  test("customer adds a photo to an in-progress request (C21)", async ({ page }) => {
    await loginAsCustomer(page, tenant, { email: JANE_EMAIL, password: CUSTOMER_PASSWORD });
    await page
      .locator(`[data-testid="request-add-photos-${leadId}"]`)
      .waitFor({ state: "visible", timeout: 30000 });

    // The web build's image picker opens a native file chooser.
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser", { timeout: 30000 }),
      tap(page, `request-add-photos-${leadId}`),
    ]);
    await chooser.setFiles({ name: "e2e-photo.png", mimeType: "image/png", buffer: TINY_PNG });

    await waitText(page, "1 photo sent to your electrician.", 60000);
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

    // Quote-less job: job-create-invoice no longer invoices inline — it opens
    // the AI invoice-create page (review/adjust lines → submit). Jobs that DO
    // have a quote still convert their quote lines in place; this seeded job
    // has none, which is the path that regressed.
    await tap(page, "job-create-invoice");
    await waitText(page, "New invoice");
    // Add one line by hand so the group stays deterministic (no live LLM).
    await fill(page, "invoice-line-description-0", "E2E Lifecycle job");
    await fill(page, "invoice-line-price-0", "480.00");
    await tap(page, "invoice-create-submit");

    // Submit lands on the invoice detail page (draft); send it from there.
    await page
      .locator('[data-testid="invoice-send"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await tap(page, "invoice-send");
    const sent = (await waitForInvoice(tenant, "E2E Lifecycle job", "sent", 30000)) as {
      id: string;
    };

    // Sending navigates back to the job; reopen the invoice and mark it paid.
    await page.goto(`/(trade)/invoice/${sent.id}`, { waitUntil: "networkidle" });
    await page
      .locator('[data-testid="invoice-mark-paid"]')
      .waitFor({ state: "visible", timeout: 30000 });
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
    await page
      .locator('[data-testid="role-select"]')
      .waitFor({ state: "visible", timeout: 120000 });
    await tap(page, "role-electrician");
    await tap(page, "entry-register-trade");
    await waitText(page, "Onboarding", 30000);
  });

  test("owner drives the signup wizard to plan selection without a 500 (C23)", async ({ page }) => {
    const email = `signup-${Date.now()}@e2e.example.com`;
    await page.goto("/", { waitUntil: "networkidle" });
    await page
      .locator('[data-testid="role-select"]')
      .waitFor({ state: "visible", timeout: 120000 });
    await tap(page, "role-electrician");
    await tap(page, "entry-register-trade");
    await waitText(page, "Onboarding", 30000);

    // Welcome → account. The wizard's FormFields have no testIDs, so the
    // steps are driven by their placeholders/button copy.
    await tapText(page, "Create my account");
    await waitText(page, "Create your account");
    await page.getByPlaceholder("Full name").fill("E2E Signup Owner");
    await page.getByPlaceholder("you@business.com").fill(email);
    await page.getByPlaceholder("07700 123 456").fill("07700 900777");
    await page.getByPlaceholder("At least 8 characters").fill("E2E-Signup-1");
    await tapText(page, "I accept the Terms of Service");
    await tapText(page, "Continue");

    // Business identity — only the trading name is required.
    await waitText(page, "Business identity");
    await page.getByPlaceholder("e.g. Smith Electrical Ltd").fill("E2E Signup Electrical");
    await tapText(page, "Continue");

    // Address & service area — postcode + address are required.
    await waitText(page, "Address & service area");
    await page.getByPlaceholder("e.g. SK8 3NJ").fill("SK8 3NJ");
    await page.getByPlaceholder("Full trading address").fill("1 E2E Way, Cheadle");
    await tapText(page, "Continue");

    // Tax & VAT (defaults to not VAT-registered) and Compliance (all optional).
    await waitText(page, "Tax & VAT");
    await tapText(page, "Continue");
    await waitText(page, "Compliance & credentials");
    await tapText(page, "Continue");

    // Services — at least one selection is required.
    await waitText(page, "Services offered");
    await tapText(page, "Consumer unit");
    await tapText(page, "Continue");

    // Branding — keep the default colour.
    await waitText(page, "Branding");
    await tap(page, "branding-continue");

    // Review & launch — this provisions the tenant (finishRegistration).
    await waitText(page, "Review & launch");
    await tap(page, "onboarding-choose-plan");

    // The plan step must render the plan options with no internal-error
    // surface. Paddle checkout itself stays manual (device checklist).
    await waitText(page, "Choose your plan", 60000);
    await page.locator('[data-testid="plan-sole_trader"]').waitFor({ state: "visible", timeout: 30000 });
    await page.locator('[data-testid="plan-pro"]').waitFor({ state: "visible", timeout: 30000 });
    await page.locator('[data-testid="plan-team"]').waitFor({ state: "visible", timeout: 30000 });
    expect(await bodyText(page)).not.toMatch(/internal server error|\b500\b|payment setup failed/i);
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

    // While the refine runs, the line items are replaced by a skeleton with a
    // leave-page banner (C10).
    await page
      .locator('[data-testid="refine-skeleton"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await page
      .locator('[data-testid="refine-banner"]')
      .waitFor({ state: "visible", timeout: 30000 });

    // Refine calls Kimi (60-120s). Poll the API for the total to change.
    let after = before;
    const deadline = Date.now() + 240_000;
    while (Date.now() < deadline) {
      after = (await api(tenant, `/quotes/${quoteId}`)) as { total: string };
      if (after.total !== before.total) break;
      await sleep(3000);
    }
    expect(after.total, "refine did not change quote total").not.toBe(before.total);

    // The skeleton clears once the refined quote comes back.
    await page
      .locator('[data-testid="refine-skeleton"]')
      .waitFor({ state: "detached", timeout: 30000 });
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
    await page
      .locator('[data-testid="role-select"]')
      .waitFor({ state: "visible", timeout: 120000 });
    await tap(page, "role-electrician");
    await tap(page, "entry-trade-login");
    await waitText(page, "Electrician login");
    await fill(page, "login-email", engineerEmail);
    await fill(page, "login-password", engineerPassword);
    await tap(page, "login-submit");
    await waitText(page, "Dashboard", 60000);
  });
});
