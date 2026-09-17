// G18 — Arrival & intake: branded portal, quote-request form, auto-provisioned
// passwordless customer, magic-link-ready identity, entry_channel recording,
// contact-preference chips (chat-reachability gating, 5ac841a).
// G19 — Inline AI triage: sync_check intake is bounded and fail-open.
//
// Runs against the deployed landing bundle in portal mode (`?slug=` override)
// + staging API. See docs/e2e-coverage-gaps.md rows G18/G19.

import { expect, type Page } from "@playwright/test";
import {
  createTenant,
  staffApi,
  stagingConfigured,
  submitIntake,
  uniqueEmail,
  type Tenant,
  portalTest as test,
} from "./helpers";

const tenantFixtures: Array<{ tenant: Tenant; slug: string }> = [];

async function loadTenant(prefix: string): Promise<Tenant> {
  const cached = tenantFixtures.find((f) => f.slug === prefix);
  if (cached) return cached.tenant;
  const tenant = await createTenant(prefix);
  tenantFixtures.push({ tenant, slug: prefix });
  return tenant;
}

/** Open a portal page with the `?slug=` host override (B5 strategy). */
async function gotoPortal(page: Page, slug: string, path = "/"): Promise<void> {
  const joiner = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${joiner}slug=${encodeURIComponent(slug)}`, {
    waitUntil: "domcontentloaded",
  });
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  await loadTenant("portal-intake");
});

test.describe("G18 — arrival & intake", () => {
  test("tenant-branded portal renders for ?slug= and unknown slugs 404", async ({ page }) => {
    const tenant = await loadTenant("portal-intake");

    await gotoPortal(page, tenant.slug);
    await expect(page).toHaveTitle(new RegExp(tenant.name));
    // Portal chrome, not marketing content.
    await expect(page.getByText("Customer portal").first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Quotes" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Invoices" }).first()).toBeVisible();
    await expect(page.getByText("Request a quote").first()).toBeVisible();

    await gotoPortal(page, "definitely-not-a-real-tenant-xyz");
    await expect(page.getByRole("heading", { name: /can.?t find|not found/i })).toBeVisible();
  });

  test("intake form submits → lead, passwordless customer, reference, entry_channel", async ({
    page,
  }) => {
    const tenant = await loadTenant("portal-intake");
    const email = uniqueEmail("intake");
    const description = "Consumer unit keeps tripping when the shower runs";

    await gotoPortal(page, tenant.slug);
    await page.locator("#qr-name").fill("Portal Intake Customer");
    await page.locator("#qr-email").fill(email);
    await page.locator("#qr-phone").fill("07700 900123");
    // Contact-preference chips (5ac841a): prefer email.
    await page.getByRole("button", { name: "Email", exact: true }).click();
    await page.locator("#qr-address").fill("12 Portal Road");
    await page.locator("#qr-postcode").fill("M20 1AA");
    await page.locator("#qr-description").fill(description);

    // Property profile accordion.
    await page.getByRole("button", { name: /About your property/ }).click();
    await page.getByRole("button", { name: "Semi-detached", exact: true }).click();
    await page.getByRole("button", { name: "Owner", exact: true }).click();
    await page.getByRole("button", { name: "Tripping", exact: true }).click();

    // Preferred visit date.
    const date = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);
    await page.getByLabel("Pick a preferred date").fill(date);
    await page.getByRole("button", { name: "Add", exact: true }).click();

    await page.getByRole("button", { name: "Request a quote" }).click();

    // Done state with a reference (bounded — the sync_check race resolves to
    // 'done' on timeout, so either phase landing within the submit ceiling is
    // a pass here; the chat phase is asserted in the G19 spec).
    const received = page.getByText("Request received");
    const chatPhase = page.getByText("A couple of quick questions");
    await expect(received.or(chatPhase).first()).toBeVisible({ timeout: 25_000 });
    if (await received.isVisible()) {
      await expect(page.getByText(/Your reference:/)).toBeVisible();
    }

    // Server-side: lead exists with property profile + preferred dates.
    const leads = await staffApi<Array<Record<string, any>>>(tenant, "/quote-requests");
    const lead = leads.find((l) => l.raw_text === description);
    expect(lead, "lead stored").toBeTruthy();
    expect(lead!.customer_id, "auto-provisioned customer linked").toBeTruthy();
    expect((lead!.structured_data as any)?.property?.type).toBe("semi");
    expect(lead!.preferred_dates?.length).toBeGreaterThan(0);

    // The auto-provisioned account is passwordless: no password login exists.
    const login = await fetch(
      `${process.env.TEST_API_BASE_URL}/customer/login`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: tenant.slug, email, password: "any-password-1" }),
      },
    );
    expect(login.status).toBe(401);
  });

  test.fixme("QR entry channel (?ch=qr) is recorded on the lead", async ({ page }) => {
    // FIXME(product bug, do not fix in test PRs): the public intake schema
    // accepts `entry_channel` (and feeds it to the AI intake check) but the
    // QuoteRequest create never persists it — the model column
    // (models.py:1232) stays NULL. G18 requires entry_channel recorded.
    const tenant = await loadTenant("portal-intake");
    const description = "QR arrival intake job";

    await gotoPortal(page, tenant.slug, "/?ch=qr");
    await page.locator("#qr-name").fill("QR Arrival Customer");
    await page.locator("#qr-email").fill(uniqueEmail("qr"));
    await page.locator("#qr-description").fill(description);
    await page.getByRole("button", { name: "Request a quote" }).click();

    const received = page.getByText("Request received");
    const chatPhase = page.getByText("A couple of quick questions");
    await expect(received.or(chatPhase).first()).toBeVisible({ timeout: 25_000 });

    const leads = await staffApi<Array<Record<string, any>>>(tenant, "/quote-requests");
    const lead = leads.find((l) => l.raw_text === description);
    expect(lead, "lead stored").toBeTruthy();
    expect(lead!.entry_channel ?? (lead!.structured_data as any)?.entry_channel).toBe("qr");
  });

  test("phone-preferred intake requires a phone number (5ac841a)", async ({ page }) => {
    const tenant = await loadTenant("portal-intake");
    await gotoPortal(page, tenant.slug);

    await page.locator("#qr-name").fill("Phone Pref Customer");
    await page.locator("#qr-email").fill(uniqueEmail("phonepref"));
    await page.getByRole("button", { name: "Phone call", exact: true }).click();
    await page.locator("#qr-description").fill("Need a new outdoor socket");

    // Submitting with phone preferred but no number blocks with a warning.
    const submit = page.getByRole("button", { name: "Request a quote" });
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByText(/We'll need your number to call you/)).toBeVisible();

    await page.locator("#qr-phone").fill("07700 900321");
    await submit.click();
    const received = page.getByText("Request received");
    const chatPhase = page.getByText("A couple of quick questions");
    await expect(received.or(chatPhase).first()).toBeVisible({ timeout: 25_000 });
  });
});

test.describe("G19 — inline AI triage", () => {
  test("sync_check intake is bounded and fail-open", async ({ page }) => {
    const tenant = await loadTenant("portal-intake");
    const description = "Fuse box upgrade with inline AI triage check";

    // API-level sync_check probe: establishes the ack shape without UI
    // timing, so the UI assertions below only need bounded-phase logic.
    const ack = await submitIntake(tenant, {
      name: "AI Triage Probe",
      email: uniqueEmail("triage-probe"),
      description,
      syncCheck: true,
    });
    expect(["questions", "ok", "unavailable"]).toContain(ack.ai_check?.status ?? "ok");

    await gotoPortal(page, tenant.slug);
    await page.locator("#qr-name").fill("AI Triage Customer");
    await page.locator("#qr-email").fill(uniqueEmail("triage"));
    await page.locator("#qr-description").fill(description);
    await page.getByRole("button", { name: "Request a quote" }).click();

    // Bounded: the customer always lands somewhere within the submit ceiling
    // (SUBMIT_TIMEOUT_MS = 15s in PortalHome). Chat phase OR done state.
    const chatPhase = page.getByText("A couple of quick questions");
    const done = page.getByText("Request received");
    await expect(chatPhase.or(done).first()).toBeVisible({ timeout: 25_000 });

    if (await chatPhase.isVisible()) {
      // A question was asked inline — answer it; the thread must accept the
      // reply and offer the exit (C13 no-reask + closure are LLM-quality
      // asserts, covered by the backend's own tests).
      await expect(page.locator('[placeholder="Type your reply…"]')).toBeVisible();
      await page.locator('[placeholder="Type your reply…"]').fill("It trips around 7am most days.");
      await page.locator('[placeholder="Type your reply…"]').press("Enter");
      await expect(
        page.getByRole("button", { name: "No more questions — done" }),
      ).toBeVisible({ timeout: 20_000 });
      await page.getByRole("button", { name: "No more questions — done" }).click();
      await expect(done).toBeVisible();
    } else {
      // Fail-open: no AI available — the form still succeeds and the lead is
      // with the tradesperson.
      await expect(done).toBeVisible();
      const leads = await staffApi<Array<Record<string, any>>>(tenant, "/quote-requests");
      expect(leads.some((l) => l.raw_text === description)).toBeTruthy();
    }
  });
});
