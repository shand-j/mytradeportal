import { expect, Page } from "@playwright/test";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Tap an element by testID, preferring the visible instance. expo-router keeps
 * previous screens mounted (hidden) in the DOM on web, so a plain `.first()`
 * can resolve a stale hidden element.
 */
export async function tap(page: Page, testId: string, settleMs = 400): Promise<void> {
  const visible = page.locator(`[data-testid="${testId}"]:visible`).first();
  const any = page.locator(`[data-testid="${testId}"]`).first();
  const locator = (await visible.count()) > 0 ? visible : any;
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

/** Tap the visible element that renders the given (partial) text. */
export async function tapText(page: Page, text: string, settleMs = 400): Promise<void> {
  const locator = page.getByText(text, { exact: false }).locator("visible=true").first();
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

/** Wait until (partial) text is visible anywhere on the page. */
export async function waitText(page: Page, text: string, timeout = 30000): Promise<void> {
  await page
    .getByText(text, { exact: false })
    .locator("visible=true")
    .first()
    .waitFor({ state: "visible", timeout });
}

/** Fill a text input (by testID) with a value, replacing any existing text. */
export async function fill(page: Page, testId: string, value: string): Promise<void> {
  const input = page.locator(`[data-testid="${testId}"]`).locator("visible=true").first();
  await input.waitFor({ state: "visible", timeout: 20000 });
  await input.fill(value);
}

/** The current visible page text (for coarse content assertions). */
export async function bodyText(page: Page): Promise<string> {
  return page.locator("body").innerText();
}

/**
 * Fetch the customer names on the demo tenant's leads (quote requests) directly
 * from the API. Used to assert that a homeowner submission actually reached the
 * backend, independent of the (non-blocking) mobile UI.
 */
export async function fetchLeadCustomerNames(
  apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000"
): Promise<string[]> {
  const authRes = await fetch(`${apiBase}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "owner@demo.trade",
      password: "demo123",
      tenant_slug: "demo",
    }),
  });
  const auth = (await authRes.json()) as { access_token: string; user: { tenant_id: string } };
  const res = await fetch(`${apiBase}/quote-requests`, {
    headers: {
      Authorization: `Bearer ${auth.access_token}`,
      "X-Tenant-ID": auth.user.tenant_id,
    },
  });
  const rows = (await res.json()) as { customer?: { name?: string } }[];
  return rows.map((r) => r.customer?.name ?? "").filter(Boolean);
}

/** Return the backend status of the demo tenant's quote with the given title. */
export async function fetchQuoteStatus(
  title: string,
  apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000"
): Promise<string | undefined> {
  const authRes = await fetch(`${apiBase}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "owner@demo.trade", password: "demo123", tenant_slug: "demo" }),
  });
  const auth = (await authRes.json()) as { access_token: string; user: { tenant_id: string } };
  const res = await fetch(`${apiBase}/quotes`, {
    headers: {
      Authorization: `Bearer ${auth.access_token}`,
      "X-Tenant-ID": auth.user.tenant_id,
    },
  });
  const rows = (await res.json()) as { title: string; status: string }[];
  return rows.find((r) => r.title === title)?.status;
}

type AuthCtx = { token: string; tenantId: string; base: string };

async function authTrade(
  apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000"
): Promise<AuthCtx> {
  const res = await fetch(`${apiBase}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "owner@demo.trade", password: "demo123", tenant_slug: "demo" }),
  });
  const auth = (await res.json()) as { access_token: string; user: { tenant_id: string } };
  return { token: auth.access_token, tenantId: auth.user.tenant_id, base: apiBase };
}

function authHeaders(ctx: AuthCtx): Record<string, string> {
  return {
    Authorization: `Bearer ${ctx.token}`,
    "X-Tenant-ID": ctx.tenantId,
    "Content-Type": "application/json",
  };
}

/**
 * Create a fresh "sent" invoice for the demo tenant via the API and return its
 * id plus the unique line-item description (used as the card title in the app).
 * Keeps the money-loop E2E deterministic and re-runnable.
 */
export async function createSentInvoice(): Promise<{ id: string; description: string }> {
  const ctx = await authTrade();
  const contactsRes = await fetch(`${ctx.base}/contacts`, { headers: authHeaders(ctx) });
  const contacts = (await contactsRes.json()) as { id: string; name: string }[];
  const contact = contacts.find((c) => c.name === "E2E Sarah Beta") ?? contacts[0];

  const description = `E2E Money Loop ${Date.now()}`;
  const createRes = await fetch(`${ctx.base}/invoices`, {
    method: "POST",
    headers: authHeaders(ctx),
    body: JSON.stringify({
      contact_id: contact.id,
      line_items: [{ description, quantity: 1, unit_price: 500 }],
    }),
  });
  const created = (await createRes.json()) as { id: string };
  await fetch(`${ctx.base}/invoices/${created.id}/send`, {
    method: "POST",
    headers: authHeaders(ctx),
  });
  return { id: created.id, description };
}

/** Return the backend status of a specific invoice id. */
export async function fetchInvoiceStatus(id: string): Promise<string | undefined> {
  const ctx = await authTrade();
  const res = await fetch(`${ctx.base}/invoices/${id}`, { headers: authHeaders(ctx) });
  if (!res.ok) return undefined;
  const inv = (await res.json()) as { status: string };
  return inv.status;
}

/**
 * Log in as the seeded demo trade owner from the entry screen. Assumes the app
 * is in connected mode (EXPO_PUBLIC_API_BASE_URL set) with no business slug, so
 * the entry screen shows the "Electrician login" option and the login form is
 * pre-filled with the demo credentials that the seed script provisions.
 */
export async function loginAsTradeOwner(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "networkidle" });
  // First navigation triggers a cold Expo web bundle (slow, especially --clear).
  await waitText(page, "My Trade Portal", 120000);
  await tap(page, "entry-trade-login");
  await waitText(page, "Electrician login");
  await tapText(page, "Sign in");
  await waitText(page, "Top leads", 30000);
}

export { sleep, expect };
