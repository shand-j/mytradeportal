import { Page, test } from "@playwright/test";
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

// Tenant settings screens: payment details, working hours, follow-up cadence /
// rounding and the calendar-subscription entry point. Persistence is verified
// against GET /tenants/me (settings JSONB, snake_case keys).

test.describe.serial("L — Tenant settings screens", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("settings");
  });

  const openSettings = async (page: Page) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "dashboard-more");
    await waitText(page, "Customer code");
  };

  test("N27: payment details validate the sort code and persist", async ({ page }) => {
    await openSettings(page);
    await tapText(page, "Payment details");
    await waitText(page, "bank details appear on your invoice emails");

    await fill(page, "payment-account-name", "E2E Electrical Ltd");
    await fill(page, "payment-account-number", "12345678");

    // Bad sort code → inline validation error, nothing saved.
    await fill(page, "payment-sort-code", "12-34");
    await tap(page, "payment-details-save");
    await waitText(page, "Sort code must be 6 digits");

    await fill(page, "payment-sort-code", "12-34-56");
    await tap(page, "payment-details-save");
    // Saving closes the screen back to Settings.
    await waitText(page, "Customer code", 30000);

    const me = (await api(tenant, "/tenants/me")) as { settings: Record<string, unknown> };
    expect(me.settings.bank_account_name).toBe("E2E Electrical Ltd");
    expect(me.settings.bank_sort_code).toBe("12-34-56");
    expect(me.settings.bank_account_number).toBe("12345678");
  });

  test("N16: working hours screen saves days and times", async ({ page }) => {
    await openSettings(page);
    await tapText(page, "Working hours");
    // The form adopts the fetched values asynchronously — wait for the defaults
    // before editing so the fetch can't clobber the input.
    await expect(page.locator('[data-testid="working-hours-start"]')).toHaveValue("08:00", {
      timeout: 30000,
    });

    await fill(page, "working-hours-start", "09:00");
    await fill(page, "working-hours-end", "17:30");
    await tap(page, "working-hours-day-5"); // drop Saturday
    await tap(page, "working-hours-save");
    await waitText(page, "Customer code", 30000);

    const me = (await api(tenant, "/tenants/me")) as {
      settings: { working_day_start?: string; working_day_end?: string; working_days?: number[] };
    };
    expect(me.settings.working_day_start).toBe("09:00");
    expect(me.settings.working_day_end).toBe("17:30");
    expect(me.settings.working_days ?? []).not.toContain(5);
  });

  test("N6: follow-ups screen shows reminder cadence and rounding chips", async ({ page }) => {
    await openSettings(page);
    await tapText(page, "Follow-up settings");
    // Wait for the fetched cadence before interacting (defaults: 3 × every 3 days).
    await expect(page.locator('[data-testid="follow-up-quote-max"]')).toHaveValue("3", {
      timeout: 30000,
    });
    await expect(page.locator('[data-testid="follow-up-quote-interval"]')).toBeVisible();
    await expect(page.locator('[data-testid="follow-up-invoice-interval"]')).toBeVisible();
    for (const value of [0, 5, 10]) {
      await expect(page.locator(`[data-testid="follow-up-rounding-${value}"]`)).toBeVisible();
    }

    await tap(page, "follow-up-rounding-5");
    await tap(page, "follow-up-save");
    await waitText(page, "Customer code", 30000);

    const me = (await api(tenant, "/tenants/me")) as { settings: Record<string, unknown> };
    expect(Number(me.settings.quote_rounding)).toBe(5);
  });

  test("N7: calendar subscription control renders without error", async ({ page }) => {
    await openSettings(page);
    const button = page.locator('[data-testid="settings-calendar-subscription"]');
    await button.waitFor({ state: "visible", timeout: 20000 });
    // The native subscribe prompt is device-only; the settings surface itself
    // must not be showing an error. (Tapping is not exercised on web: RNW's
    // Share.share rejects in headless Chromium, which the screen would surface
    // as the error banner.)
    await expect(button).not.toContainText("Could not load your calendar link");

    const feed = (await api(tenant, "/calendar/feed-link")) as Record<string, string>;
    expect(feed.webcal_url ?? feed.webcalUrl).toBeTruthy();
  });
});
