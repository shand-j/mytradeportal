import { test, expect } from "@playwright/test";
import { tap, waitText, bodyText, fetchLeadCustomerNames } from "./helpers";

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
