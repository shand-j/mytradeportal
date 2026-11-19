import { test, type Route } from "@playwright/test";
import {
  bodyText,
  createTestTenant,
  expect,
  loginAsTradeOwner,
  Tenant,
  waitText,
} from "./helpers";

/**
 * DEFECT-013/014 regression — billing enforcement + paywall copy.
 *
 * DEFECT-013: the only /paywall redirect used to live in app/index.tsx, which
 * unmounts before a canceled tenant's first gated call 402s. The gate now
 * lives in app/(trade)/_layout.tsx, so any 402 routes to /paywall wherever it
 * lands. Cancellation is a Paddle portal action (no API to cancel), so the
 * canceled-tenant state is simulated at the network layer: the dashboard's
 * first gated fetch 402s exactly as SubscriptionPaywallMiddleware answers,
 * and /billing/subscription reports the canceled subscription.
 *
 * DEFECT-014: the paywall copy must resolve the server's tier plan keys
 * (sole_trader/pro/team) — not just the legacy keys — so the plan name and
 * the pricing line render instead of "your undefined plan".
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

  test("a 402 after login routes to the paywall, which renders the plan name and pricing", async ({
    page,
  }) => {
    test.setTimeout(300_000);

    // Register the mocks before login so the dashboard's first gated fetches
    // 402 after index.tsx has already routed away and unmounted — the case
    // DEFECT-013 left uncovered.
    await page.route("**/billing/subscription", json(200, CANCELED_SUBSCRIPTION));
    await page.route("**/analytics/dashboard", json(402, { detail: "subscription_required" }));
    await page.route("**/jobs", json(402, { detail: "subscription_required" }));

    await loginAsTradeOwner(page, tenant);

    // The trade layout's global 402 gate routes to /paywall as soon as a
    // gated call is answered — the dashboard must not remain usable.
    await page.waitForURL(/paywall/, { timeout: 60000 });
    await waitText(page, "Subscription required", 30000);

    // DEFECT-014: plan_key "sole_trader" (a tier key) must resolve to a plan
    // name and pricing line — the copy must never render "undefined".
    const body = await bodyText(page);
    expect(body).not.toContain("undefined");
    expect(body).toContain("Sole Trader");
    expect(body).toContain("£25/month");
    expect(body).toContain("Subscribe at mytradeportal.co.uk");
  });
});
