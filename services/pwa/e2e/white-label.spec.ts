import { test, expect } from "@playwright/test";
import { tap, tapText, waitText, bodyText, fill, fetchLeadCustomerNames } from "./helpers";

// A per-tenant white-label build (EXPO_PUBLIC_BUSINESS_SLUG set) fetches the
// business's public config on launch and opens branded for that tenant, rather
// than the generic marketplace 6-digit code entry.

test("app boots branded from the real public config", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await waitText(page, "Your electrician", 60000);

  const body = await bodyText(page);
  expect(body).toMatch(/Demo Electrical/); // real tenant name from the API
  expect(body).toMatch(/Request a quote/); // branded customer entry
  expect(body).not.toMatch(/6-digit code/); // not the generic marketplace screen
});

test("a homeowner can submit a quote request that reaches the trade backend", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await waitText(page, "Your electrician", 60000);

  await tap(page, "entry-request-quote");
  // The wizard is pre-filled with demo data (postcode, contact, property,
  // category=consumer_unit), so each step advances via its Continue button.
  await tap(page, "quote-check-area");
  await tap(page, "quote-contact-continue");
  await tap(page, "quote-property-continue");
  await tap(page, "quote-category-continue");
  await tap(page, "quote-consumer-unit-continue");
  await tap(page, "quote-media-continue");
  await tap(page, "quote-urgency-continue");
  await tap(page, "quote-budget-continue");
  // Consents gate the submit button.
  await tap(page, "quote-consent-terms");
  await tap(page, "quote-consent-contact");
  await tap(page, "quote-submit");

  await waitText(page, "has your request", 30000); // confirmation screen

  // The submit is non-blocking in the UI, so poll the API to prove the request
  // actually reached the backend as a lead.
  await expect
    .poll(async () => (await fetchLeadCustomerNames()).includes("Jane Homeowner"), {
      timeout: 20000,
    })
    .toBe(true);
});

test("a homeowner can register, then see their submitted request in their history", async ({
  page,
}) => {
  const email = `e2e.homeowner.${Date.now()}@example.com`;
  const password = "homeowner-pass-123";

  await page.goto("/", { waitUntil: "networkidle" });
  await waitText(page, "Your electrician", 60000);

  // Customer login -> switch to register -> create a real account.
  await tap(page, "entry-customer-login");
  await waitText(page, "Customer login");
  await tap(page, "login-toggle-mode");
  await waitText(page, "Create your account");
  await fill(page, "login-name", "E2E Homeowner");
  await fill(page, "login-phone", "07700 900999");
  await fill(page, "login-email", email);
  await fill(page, "login-password", password);
  await tap(page, "login-submit");

  // Lands on the customer's quotes/requests screen (empty history).
  await waitText(page, "My quotes", 30000);

  // Submit a quote request while logged in — it should link to this customer.
  await tap(page, "request-new-quote");
  await tap(page, "quote-check-area");
  await tap(page, "quote-contact-continue");
  await tap(page, "quote-property-continue");
  await tap(page, "quote-category-continue");
  await tap(page, "quote-consumer-unit-continue");
  await tap(page, "quote-media-continue");
  await tap(page, "quote-urgency-continue");
  await tap(page, "quote-budget-continue");
  await tap(page, "quote-consent-terms");
  await tap(page, "quote-consent-contact");
  await tap(page, "quote-submit");
  await waitText(page, "has your request", 30000);
  await tap(page, "quote-done");

  // Back on the history screen, the request now appears (from the customer's
  // own /customer/quote-requests, proving the account + linkage).
  await waitText(page, "My quotes", 30000);
  await waitText(page, "Consumer unit", 30000);
});
