import { test, expect } from "@playwright/test";
import { tap, tapText, waitText, bodyText, loginAsTradeOwner, fetchQuoteStatus } from "./helpers";

// These exercise the mobile app against a real API (connected mode). They prove
// the wired read pattern and the onboarding write flow end-to-end.

test.describe("trade connected mode", () => {
  test("login lands on a live dashboard", async ({ page }) => {
    await loginAsTradeOwner(page);
    // The outstanding-quotes card shows a LIVE badge only when the real /quotes
    // query succeeds, so its presence proves the dashboard is backend-driven.
    await expect(page.getByText("LIVE", { exact: true }).first()).toBeVisible();
    expect(await bodyText(page)).toMatch(/Outstanding quotes/);
  });

  test("quotes list shows the seeded quote from the API", async ({ page }) => {
    await loginAsTradeOwner(page);
    await tap(page, "tab-quotes");
    await waitText(page, "Quotes / Leads");
    await waitText(page, "E2E Consumer unit upgrade");
    await expect(page.getByText("LIVE", { exact: true }).first()).toBeVisible();
  });

  test("calendar shows the seeded job from the API", async ({ page }) => {
    await loginAsTradeOwner(page);
    await tap(page, "tab-calendar");
    await waitText(page, "Bookings");
    await waitText(page, "E2E EV charger install");
  });

  test("a lead submitted from the customer app appears on the leads list", async ({ page }) => {
    await loginAsTradeOwner(page);
    await tap(page, "tab-quotes");
    await waitText(page, "Quotes / Leads");
    // Seeded via the public /businesses/{slug}/quote-requests endpoint.
    await waitText(page, "E2E Landlord EICR");
  });

  test("opening a real lead shows its detail with the AI-quote action", async ({ page }) => {
    await loginAsTradeOwner(page);
    await tap(page, "tab-quotes");
    await waitText(page, "E2E Landlord EICR");
    // Tapping a real lead (UUID id) must resolve the backend lead, not a mock.
    await tapText(page, "E2E Landlord EICR");
    await waitText(page, "Generate AI quote", 30000);
  });

  test("approving and sending a quote updates it on the backend", async ({ page }) => {
    await loginAsTradeOwner(page);
    await tap(page, "tab-quotes");
    await waitText(page, "E2E Consumer unit upgrade");
    // Open the real quote and send it.
    await tapText(page, "E2E Consumer unit upgrade");
    await waitText(page, "Review AI quote", 30000);
    await tap(page, "quote-approve-send");
    await waitText(page, "Quotes / Leads", 30000); // returned to the list

    await expect
      .poll(async () => fetchQuoteStatus("E2E Consumer unit upgrade"), { timeout: 20000 })
      .toBe("sent");
  });

  test("registering a business provisions a real tenant and reaches the dashboard", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await waitText(page, "My Trade Portal", 120000);

    await tap(page, "entry-register-trade");
    await waitText(page, "Create my account", 30000);
    await tapText(page, "Create my account");

    // account -> identity -> address -> tax -> compliance all use pre-filled
    // demo values, so a single "Continue" advances each.
    await waitText(page, "Create your account", 30000);
    for (let i = 0; i < 5; i++) {
      const cont = page.getByText("Continue", { exact: false }).locator("visible=true").first();
      await cont.waitFor({ state: "visible" });
      await cont.click({ force: true });
      await page.waitForTimeout(500);
    }

    // services requires at least one selection before Continue is enabled.
    await waitText(page, "Services offered");
    await tapText(page, "EV charger");
    const cont = page.getByText("Continue", { exact: false }).locator("visible=true").first();
    await cont.click({ force: true });

    // review -> plan -> (simulated) checkout -> dashboard.
    await tap(page, "onboarding-choose-plan");
    await tap(page, "plan-continue");
    await tap(page, "payment-go-dashboard", 1200);

    // Provisioning runs several sequential API calls (create tenant, login,
    // record steps, launch) before navigating, so allow generous headroom.
    await waitText(page, "Top leads", 60000);
  });
});
