import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  fill,
  loginAsTradeOwner,
  tap,
  tapText,
  Tenant,
  waitText,
} from "./helpers";

// Google review URL capture (G14): the Branding settings screen round-trips
// ``review_url`` onto the tenant (settings JSONB), the white-label public
// config exposes it (the customer portal + payment-received review CTA read
// it from there), and the Quotes screen share sheet encodes the tenant's
// portal link for customers to scan/share.

const REVIEW_URL = "https://g.page/r/CcE2eBranding/review";

test.describe.serial("R — Review URL capture & share", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("branding");
  });

  test("G14: branding screen persists review_url on the tenant and public config", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "dashboard-more");
    await waitText(page, "Customer code");
    await tapText(page, "Business profile & branding");
    await waitText(page, "Branding");

    await fill(page, "branding-review-url", REVIEW_URL);
    await tap(page, "branding-save");
    // Saving closes back to the Settings list.
    await waitText(page, "Customer code", 30_000);

    const me = (await api(tenant, "/tenants/me")) as { settings: Record<string, unknown> };
    expect(me.settings.review_url).toBe(REVIEW_URL);

    // The portal/public consumers read it from the white-label public config.
    // (The API serialises the public config camelCase.)
    const config = (await api(tenant, `/businesses/${tenant.slug}/public-config`, {
      auth: false,
    })) as { review_url?: string | null; reviewUrl?: string | null };
    expect(config.review_url ?? config.reviewUrl).toBe(REVIEW_URL);
  });

  test("G14: Quotes share sheet encodes the tenant portal link", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto("/(trade)/quotes", { waitUntil: "networkidle" });
    // The share CTA renders in the empty state; this tenant has no quotes yet.
    await tap(page, "share-qr-button");
    await page.locator('[data-testid="qr-modal"]').waitFor({ state: "visible", timeout: 20000 });

    const portalUrl = `https://${tenant.slug}.mytradeportal.co.uk`;
    await expect(page.locator('[data-testid="portal-url"]')).toHaveText(portalUrl, {
      timeout: 20000,
    });
    await page.locator('[data-testid="portal-qr-code"]').waitFor({
      state: "visible",
      timeout: 20000,
    });
    // The share-link button carries the same portal URL (RNW Share is a no-op
    // on web — the button's enabled state encodes the URL is ready).
    await expect(page.locator('[data-testid="qr-share-link"]')).toBeEnabled();
  });
});
