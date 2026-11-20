import { test, type Route } from "@playwright/test";
import {
  bodyText,
  createTestTenant,
  expect,
  fill,
  loginAsCustomer,
  loginAsTradeOwner,
  seedCustomer,
  seedLead,
  seedSentQuote,
  tap,
  Tenant,
  waitText,
} from "./helpers";

const CUSTOMER_PASSWORD = "E2E-Customer-1";

// Trade messaging: new-message picker over account-holding customers and the
// quote screen's request-more-info shortcut into the customer chat.

test.describe.serial("N — Messages", () => {
  let tenant: Tenant;
  let customer: { email: string; fullName: string };
  let contactId: string;
  let quote: { id: string; title: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("messages");
    customer = { email: "msg-customer@e2e.example.com", fullName: "E2E Msg Customer" };
    const lead = await seedLead(tenant, {
      title: "E2E Messages lead",
      category: "consumer_unit",
      contact: {
        name: customer.fullName,
        email: customer.email,
        phone: "07700 900666",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registration = await seedCustomer(tenant, {
      email: customer.email,
      password: CUSTOMER_PASSWORD,
      fullName: customer.fullName,
      phone: "07700 900666",
      quoteRequestId: lead.id,
    });
    contactId = registration.customer.contact_id;
    quote = await seedSentQuote(tenant, {
      title: "E2E Messages quote",
      contactId,
      quoteRequestId: lead.id,
    });
  });

  test("N29: new-message search finds an account-holding customer and opens the thread", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "tab-messages");
    await page
      .locator('[data-testid="new-message-button"]')
      .waitFor({ state: "visible", timeout: 30000 });

    await tap(page, "new-message-button");
    await page
      .locator('[data-testid="new-message-search"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await fill(page, "new-message-search", "E2E Msg Customer");
    await tap(page, `new-message-contact-${contactId}`);

    // The direct thread opens on the messages screen.
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30000 });
  });

  test("C7: request-more-info from a quote opens the customer chat", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/quote/${quote.id}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote");

    await tap(page, "quote-more-actions");
    await tap(page, "quote-request-info");
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30000 });
  });
});

test.describe.serial("Customer AI follow-up recovery", () => {
  let tenant: Tenant;
  let quoteRequestId: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("messages-ai-recovery");
    const lead = await seedLead(tenant, {
      title: "E2E AI recovery lead",
      category: "lighting",
      contact: {
        name: "E2E Recovery Customer",
        email: "messages-ai-recovery@e2e.example.com",
        phone: "07700 900777",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    quoteRequestId = lead.id;
    await seedCustomer(tenant, {
      email: "messages-ai-recovery@e2e.example.com",
      password: CUSTOMER_PASSWORD,
      fullName: "E2E Recovery Customer",
      phone: "07700 900777",
      quoteRequestId,
    });
  });

  test("shows recovery UI after failure and retries without duplicating the request", async ({
    page,
  }) => {
    const existingMessage = {
      id: "customer-message-existing",
      tenant_id: tenant.tenantId,
      contact_id: null,
      quote_request_id: quoteRequestId,
      channel: "in_app_chat",
      direction: "inbound",
      sender_role: "customer",
      subject: null,
      body: "The kitchen ceiling lights flicker in the evening.",
      status: "sent",
      ai_metadata: null,
      created_at: "2026-11-20T10:00:00Z",
    };
    const aiMessage = {
      ...existingMessage,
      id: "ai-message-retry-success",
      direction: "outbound",
      sender_role: "ai",
      body: "Do all of the kitchen lights flicker, or only one fitting?",
      ai_metadata: { complete: false },
      created_at: "2026-11-20T10:01:00Z",
    };
    let aiReplyAvailable = false;
    let followupRequests = 0;

    await page.route(
      "**/communications?quote_request_id=*",
      async (route: Route) => {
        const request = route.request();
        if (
          request.method() !== "GET" ||
          new URL(request.url()).searchParams.get("quote_request_id") !== quoteRequestId
        ) {
          await route.continue();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(aiReplyAvailable ? [existingMessage, aiMessage] : [existingMessage]),
        });
      }
    );
    await page.route(
      `**/communications/${quoteRequestId}/ai-followup`,
      async (route: Route) => {
        followupRequests += 1;
        if (followupRequests === 1) {
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "AI provider unavailable" }),
          });
          return;
        }
        aiReplyAvailable = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(aiMessage),
        });
      }
    );

    await loginAsCustomer(page, tenant, {
      email: "messages-ai-recovery@e2e.example.com",
      password: CUSTOMER_PASSWORD,
    });
    await page.goto(`/(customer)/messages?quoteRequestId=${quoteRequestId}`);

    const error = page.getByTestId("chat-followup-error");
    await expect(error).toBeVisible();
    await expect(page.getByText(existingMessage.body, { exact: true })).toBeVisible();
    await expect(page.getByTestId("chat-followup-retry")).toBeVisible();
    await expect(page.getByTestId("chat-followup-message")).toBeVisible();
    await expect(page.getByTestId("chat-composer")).toBeVisible();
    await expect(page.getByText("No messages yet", { exact: false })).toHaveCount(0);
    expect(followupRequests).toBe(1);

    await page
      .getByTestId("chat-followup-retry")
      .evaluate((button: HTMLElement) => {
        button.click();
        button.click();
      });

    await expect(page.getByText(aiMessage.body, { exact: true })).toBeVisible();
    await expect(error).toBeHidden();
    await expect(page.getByTestId("chat-message-ai")).toHaveCount(0);
    await expect(page.getByTestId("chat-message-agent")).toHaveCount(1);
    expect(followupRequests).toBe(2);
  });
});

// N24: a fresh tenant with no quote requests or threads must see the designed
// inbox empty state — not a blank screen or an error. Own tenant so the inbox
// is guaranteed empty (the N-suite tenant above seeds a lead).
test.describe("N24 — Empty inbox", () => {
  test("empty inbox renders the designed empty state", async ({ page }) => {
    const tenant = await createTestTenant("messages-empty");
    await loginAsTradeOwner(page, tenant);
    await tap(page, "tab-messages");

    await waitText(page, "No conversations yet — new quote requests will appear here.");
    const text = (await bodyText(page)).toLowerCase();
    expect(text).not.toContain("something went wrong");
    expect(text).not.toContain("could not load");
  });
});
