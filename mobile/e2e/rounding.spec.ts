import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  loginAsTradeOwner,
  seedContact,
  tap,
  tapText,
  Tenant,
  waitText,
} from "./helpers";

// Rounding & VAT chain (G29, P0): the Follow-ups rounding chip (£5/£10)
// rounds quote totals UP with the uplift persisted on ``rounding_adjustment``;
// quote → job → invoice mirrors the quote's totals EXACTLY (never re-rounded).
// Both VAT directions are encoded (N22 was marked Fail in the backlog):
// a VAT-registered tenant charges 20%, a non-registered tenant charges 0%
// on every line/total when the client leaves ``vat_rate`` unset.

const money = (value: unknown) => Number(value);

test.describe.serial("Q — Rounding & VAT chain", () => {
  let tenant: Tenant; // VAT-registered, rounding £5
  let novat: Tenant; // non-VAT-registered, rounding £10
  let contactId: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("rounding");
    novat = await createTestTenant("novat");
    contactId = (await seedContact(tenant, { name: "E2E Rounding Customer" })).id as string;
  });

  // Drive the real rounding chip in the Follow-ups settings screen so the
  // chain starts from UI state, exactly as a tradesperson would set it.
  test("G29: the rounding chip persists quote_rounding=5 on the tenant", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await tap(page, "dashboard-more");
    await waitText(page, "Customer code");
    await tapText(page, "Follow-up settings");
    await expect(page.locator('[data-testid="follow-up-quote-max"]')).toHaveValue("3", {
      timeout: 30_000,
    });
    await tap(page, "follow-up-rounding-5");
    await tap(page, "follow-up-save");
    await waitText(page, "Customer code", 30_000);

    const me = (await api(tenant, "/tenants/me")) as { settings: Record<string, unknown> };
    expect(Number(me.settings.quote_rounding)).toBe(5);
  });

  test("G29: VAT-registered tenant — quote rounds up to £5 and the invoice mirrors it exactly", async () => {
    // Register the tenant for VAT (onboarding Tax step) — new quotes without
    // an explicit vat_rate then fall through to the UK standard 20%.
    await api(tenant, "/onboarding/step/tax", {
      method: "PATCH",
      body: { step: "tax", value: { vat_registered: true, vat_number: "GB123456789", vat_scheme: "standard" } },
    });

    // £63.00 + 20% VAT = £75.60 → rounds UP to £80.00 (uplift £4.40).
    const quote = await api(tenant, "/quotes", {
      method: "POST",
      body: {
        contact_id: contactId,
        title: "E2E Rounded VAT quote",
        line_items: [{ description: "Consumer unit replacement", quantity: 1, unit_price: 63 }],
      },
    });
    expect(money(quote.vat_rate)).toBe(0.2);
    expect(money(quote.subtotal)).toBe(63);
    expect(money(quote.vat_amount)).toBeCloseTo(12.6, 2);
    expect(money(quote.total)).toBe(80);
    expect(money(quote.rounding_adjustment)).toBeCloseTo(4.4, 2);

    await api(tenant, `/quotes/${quote.id}/approve`, { method: "POST", body: { approved: true } });
    const scheduled = new Date();
    scheduled.setDate(scheduled.getDate() + 2);
    const pad = (n: number) => String(n).padStart(2, "0");
    const slot = `${scheduled.getFullYear()}-${pad(scheduled.getMonth() + 1)}-${pad(
      scheduled.getDate()
    )}T09:00:00`;
    const job = await api(tenant, `/quotes/${quote.id}/convert-to-job`, {
      method: "POST",
      body: { scheduled_start: slot, scheduled_end: `${slot.slice(0, 11)}11:00:00` },
    });
    expect(job.quote_id).toBe(quote.id);

    // The invoice inherits the quote totals VERBATIM — same subtotal, VAT,
    // total and rounding_adjustment; it is never re-rounded.
    const invoice = await api(tenant, "/invoices", {
      method: "POST",
      body: { contact_id: contactId, job_id: job.id },
    });
    expect(money(invoice.subtotal)).toBe(money(quote.subtotal));
    expect(money(invoice.vat_amount)).toBe(money(quote.vat_amount));
    expect(money(invoice.total)).toBe(money(quote.total));
    expect(money(invoice.rounding_adjustment)).toBe(money(quote.rounding_adjustment));
    // Sanity: the mirror is the ROUNDED total, not the raw £75.60.
    expect(money(invoice.total)).toBe(80);
  });

  test("G29: non-VAT-registered tenant — 0% VAT on all totals, rounding still applies and mirrors", async () => {
    await api(novat, "/onboarding/step/tax", {
      method: "PATCH",
      body: { step: "tax", value: { vat_registered: false } },
    });
    await api(novat, "/tenants/me", {
      method: "PATCH",
      body: { settings: { quote_rounding: 10 } },
    });

    const contact = await seedContact(novat, { name: "E2E NoVAT Customer" });
    // £102.00, no VAT → rounds UP to £110.00 (uplift £8.00).
    const quote = await api(novat, "/quotes", {
      method: "POST",
      body: {
        contact_id: contact.id,
        title: "E2E NoVAT rounded quote",
        line_items: [{ description: "Socket relocation", quantity: 1, unit_price: 102 }],
      },
    });
    expect(money(quote.vat_rate)).toBe(0);
    expect(money(quote.vat_amount)).toBe(0);
    // £102.00, no VAT → rounds UP to £110.00 (uplift £8.00).
    expect(money(quote.subtotal)).toBe(102);
    expect(money(quote.total)).toBe(110);
    expect(money(quote.rounding_adjustment)).toBe(8);

    await api(novat, `/quotes/${quote.id}/approve`, { method: "POST", body: { approved: true } });
    const scheduled = new Date();
    scheduled.setDate(scheduled.getDate() + 2);
    const pad = (n: number) => String(n).padStart(2, "0");
    const slot = `${scheduled.getFullYear()}-${pad(scheduled.getMonth() + 1)}-${pad(
      scheduled.getDate()
    )}T09:00:00`;
    const job = await api(novat, `/quotes/${quote.id}/convert-to-job`, {
      method: "POST",
      body: { scheduled_start: slot, scheduled_end: `${slot.slice(0, 11)}11:00:00` },
    });
    const invoice = await api(novat, "/invoices", {
      method: "POST",
      body: { contact_id: contact.id, job_id: job.id },
    });
    expect(money(invoice.vat_rate)).toBe(0);
    expect(money(invoice.vat_amount)).toBe(0);
    expect(money(invoice.total)).toBe(money(quote.total));
    expect(money(invoice.rounding_adjustment)).toBe(money(quote.rounding_adjustment));
  });
});
