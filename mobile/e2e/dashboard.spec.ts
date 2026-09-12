import { test } from "@playwright/test";
import {
  createTestTenant,
  expect,
  loginAsTradeOwner,
  seedBusinessServices,
  seedLead,
  tap,
  Tenant,
  waitText,
} from "./helpers";

// Dashboard composition and trade-tab navigation chrome.

test.describe.serial("M — Dashboard & navigation", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("dashboard");
    await seedBusinessServices(tenant);
    // Three new leads — the "Top new quotes" section must cap at two cards.
    for (let i = 1; i <= 3; i++) {
      await seedLead(tenant, {
        title: `E2E Dashboard lead ${i}`,
        category: "consumer_unit",
        contact: {
          name: `E2E Dash Customer ${i}`,
          email: `dash-lead-${i}@e2e.example.com`,
          phone: "07700 900555",
          postcode: "SK8 3NJ",
        },
        urgency: "this_week",
        structuredData: {
          property: { type: "detached", age: "post_2000", bedrooms: 3, parking: true },
          questionnaire: { consumer_unit: { circuits: "8" } },
        },
      });
    }
  });

  test("N30/N31: top-new-quotes section caps at two cards; no New lead button", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await waitText(page, "Top new quotes");

    // N30: the dashboard no longer offers a manual "New lead" entry point.
    await expect(page.getByText("New lead", { exact: false })).toHaveCount(0);

    // N31: exactly the best two new quotes are shown (three were seeded).
    await expect(page.locator('[data-testid^="lead-card-"]')).toHaveCount(2, {
      timeout: 30000,
    });
  });

  test("N32: revenue summary and hours-saved card render", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await waitText(page, "Revenue");
    await waitText(page, "Paid this month");
    await waitText(page, "Outstanding invoices");
    await page
      .locator('[data-testid="dashboard-time-saved-card"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await waitText(page, "Hours saved by AI");
  });

  test("N33: outstanding-quotes card navigates to quotes with the New filter active", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "dashboard-outstanding-quotes-card");
    await waitText(page, "All quotes in one place", 30000);

    expect(page.url()).toContain("filter=new");
    const newChip = page.locator('[data-testid="quotes-filter-new"]');
    await newChip.waitFor({ state: "visible", timeout: 20000 });
    // The active filter chip carries the highlighted background class.
    await expect(newChip).toHaveClass(/bg-primary-100/);
  });

  test("C16/C18/N20: tab chrome — settings menu, messages tab, calendar new-job", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);

    // Dashboard: three-dots settings shortcut in the header.
    await page
      .locator('[data-testid="dashboard-more"]')
      .waitFor({ state: "visible", timeout: 30000 });

    await tap(page, "tab-quotes");
    await page
      .locator('[data-testid="header-settings"]')
      .waitFor({ state: "visible", timeout: 30000 });

    await tap(page, "tab-customers");
    await page
      .locator('[data-testid="customers-search"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await page
      .locator('[data-testid="header-settings"]')
      .waitFor({ state: "visible", timeout: 30000 });

    await tap(page, "tab-calendar");
    await page
      .locator('[data-testid="calendar-more"]')
      .waitFor({ state: "visible", timeout: 30000 });
    // N20: borderless "+" new-job shortcut on the calendar.
    await page
      .locator('[data-testid="calendar-new-job"]')
      .waitFor({ state: "visible", timeout: 20000 });

    // C18: the messages tab exists and lands on the inbox.
    await tap(page, "tab-messages");
    await page
      .locator('[data-testid="new-message-button"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await page
      .locator('[data-testid="header-settings"]')
      .waitFor({ state: "visible", timeout: 30000 });
  });
});
