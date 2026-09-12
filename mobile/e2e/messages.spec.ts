import { test } from "@playwright/test";
import {
  createTestTenant,
  fill,
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

    await tap(page, "quote-request-info");
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30000 });
  });
});
