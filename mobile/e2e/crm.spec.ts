import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  fill,
  loginAsTradeOwner,
  tap,
  Tenant,
  waitText,
} from "./helpers";

// CRM customer record: edit round-trip, quote-intake prefill, trust badges and
// blocking. Contacts and badge state are seeded/mutated over the API.

test.describe.serial("K — CRM customer record", () => {
  let tenant: Tenant;
  let contact: { id: string; name: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("crm");
    contact = await api(tenant, "/contacts", {
      method: "POST",
      body: {
        name: "E2E CRM Customer",
        email: "crm-customer@e2e.example.com",
        phone: "07700 900444",
        postcode: "SK8 3NJ",
        address: "1 CRM Road, Stockport",
      },
    });
  });

  test("N25: customer edit round-trip persists and prefills quote intake", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto("/(trade)/customers", { waitUntil: "networkidle" });

    await tap(page, `contact-card-${contact.id}`);
    await tap(page, `contact-open-detail-${contact.id}`);
    await waitText(page, "Customer since");

    await fill(page, "customer-edit-address", "12 E2E Lane, Stockport");
    await fill(page, "customer-edit-parking", "Driveway for one van");
    await fill(page, "customer-edit-access", "Key safe code 4321");
    await tap(page, "customer-edit-save");
    await page
      .locator('[data-testid="customer-edit-saved"]')
      .waitFor({ state: "visible", timeout: 20000 });

    // Reload and confirm the record persisted server-side.
    await page.reload({ waitUntil: "networkidle" });
    await expect(page.locator('[data-testid="customer-edit-address"]')).toHaveValue(
      "12 E2E Lane, Stockport",
      { timeout: 30000 }
    );
    await expect(page.locator('[data-testid="customer-edit-parking"]')).toHaveValue(
      "Driveway for one van"
    );
    await expect(page.locator('[data-testid="customer-edit-access"]')).toHaveValue(
      "Key safe code 4321"
    );

    // The saved parking/access notes pre-fill the quote intake for this customer.
    await tap(page, "customer-detail-create-quote");
    await waitText(page, "Quote intake", 30000);
    await expect(page.locator('[data-testid="intake-parking"]')).toHaveValue(
      "Driveway for one van",
      { timeout: 30000 }
    );
    await expect(page.locator('[data-testid="intake-access"]')).toHaveValue("Key safe code 4321");
  });

  test("N26: badge chips, tri-state override and blocked banner", async ({ page }) => {
    // Force a badge on so it renders as a chip on the CRM card.
    await api(tenant, `/contacts/${contact.id}`, {
      method: "PATCH",
      body: { badge_overrides: { late_payer: true } },
    });

    await loginAsTradeOwner(page, tenant);
    await page.goto("/(trade)/customers", { waitUntil: "networkidle" });
    const card = page.locator(`[data-testid="contact-card-${contact.id}"]`);
    await card
      .locator('[data-testid="badge-late_payer"]')
      .waitFor({ state: "visible", timeout: 30000 });

    await tap(page, `contact-card-${contact.id}`);
    await tap(page, `contact-open-detail-${contact.id}`);
    await waitText(page, "Trust badges");

    // Tri-state override: forcing the badge off clears it from the effective list.
    await tap(page, "badge-late_payer-off");
    const deadline = Date.now() + 30000;
    let cleared: { badges: string[]; badge_overrides: Record<string, boolean | null> } | undefined;
    while (Date.now() < deadline) {
      const fresh = (await api(tenant, `/contacts/${contact.id}`)) as {
        badges: string[];
        badge_overrides: Record<string, boolean | null>;
      };
      if (fresh.badge_overrides?.late_payer === false && !fresh.badges.includes("late_payer")) {
        cleared = fresh;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    expect(cleared, "badge override did not persist").toBeTruthy();

    // The block button renders, but its confirm dialog is Alert.alert — a
    // native-only API that is a no-op on web. Block via the API and verify the
    // blocked state the detail screen renders.
    await page
      .locator('[data-testid="customer-block"]')
      .waitFor({ state: "visible", timeout: 20000 });
    await api(tenant, `/contacts/${contact.id}/block`, {
      method: "POST",
      body: { reason: "E2E block" },
    });
    await page.reload({ waitUntil: "networkidle" });
    await page
      .locator('[data-testid="customer-blocked-banner"]')
      .waitFor({ state: "visible", timeout: 30000 });
    await page
      .locator('[data-testid="badge-blocked"]')
      .waitFor({ state: "visible", timeout: 20000 });
    await page
      .locator('[data-testid="customer-unblock"]')
      .waitFor({ state: "visible", timeout: 20000 });
  });
});
