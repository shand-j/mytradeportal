import { test, type Route } from "@playwright/test";
import {
  bodyText,
  createTestTenant,
  expect,
  fill,
  gotoEntryRole,
  tap,
  Tenant,
  waitText,
} from "./helpers";

/**
 * Free-beta regression — legacy canceled subscriptions and stale 402 responses
 * must not route users into a Paddle paywall. The canceled state is simulated
 * at the network layer; the feature-flag response remains the real fail-closed
 * default used by the beta environment.
 */

const CANCELED_SUBSCRIPTION = {
  id: "sub-e2e-paywall",
  plan_key: "sole_trader",
  status: "canceled",
  paddle_subscription_id: null,
  paddle_customer_id: null,
  trial_ends_at: null,
  current_period_start: null,
  current_period_end: null,
  scheduled_change_action: null,
  scheduled_change_at: null,
  canceled_at: "2026-10-01T00:00:00Z",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  seats: 1,
  seats_in_use: 1,
};

const json = (status: number, payload: unknown) => (route: Route) =>
  route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });

test.describe("Paywall — billing enforcement (DEFECT-013/014)", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    test.setTimeout(300_000);
    tenant = await createTestTenant("paywall");
  });

  test("a canceled subscription and stale 402 cannot lock out a free-beta user", async ({
    page,
  }) => {
    test.setTimeout(300_000);

    // Simulate a legacy canceled subscription and a stale 402 response. The
    // server-side free-beta gate and the client must both refuse to lock out.
    await page.route("**/billing/subscription", json(200, CANCELED_SUBSCRIPTION));
    await page.route("**/analytics/dashboard", json(402, { detail: "subscription_required" }));
    await page.route("**/jobs", json(402, { detail: "subscription_required" }));

    await gotoEntryRole(page, "trade");
    await tap(page, "entry-trade-login");
    await waitText(page, "Electrician login");
    await fill(page, "login-email", tenant.adminEmail);
    await fill(page, "login-password", tenant.adminPassword);
    await tap(page, "login-submit");

    await page.waitForURL(/dashboard/, { timeout: 60000 });
    await waitText(page, "Dashboard", 30000);
    expect(page.url()).not.toContain("paywall");
    const body = await bodyText(page);
    expect(body).not.toContain("Subscription required");
    expect(body).not.toContain("Subscribe at mytradeportal.co.uk");
    expect(body).not.toContain("undefined");
  });
});
