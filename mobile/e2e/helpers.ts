import { expect, Page } from "@playwright/test";

export type Tenant = {
  slug: string;
  code: string;
  adminEmail: string;
  adminPassword: string;
  adminName: string;
  token: string;
  tenantId: string;
  base: string;
};

export type LoginCredentials = { email: string; password: string };

export const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export { expect };

async function loadCreateTenant(): Promise<(prefix?: string) => Promise<Tenant>> {
  // @ts-ignore: Node ESM helper loaded at runtime.
  const mod = (await import("./create-tenant.mjs")) as { createTenant: (prefix?: string) => Promise<Tenant> };
  return mod.createTenant;
}

async function loadSeedHelpers(): Promise<Record<string, (...args: any[]) => any>> {
  // @ts-ignore: Node ESM helper loaded at runtime.
  return (await import("./seed-e2e.mjs")) as Record<string, (...args: any[]) => any>;
}

export async function createTestTenant(prefix?: string): Promise<Tenant> {
  const create = await loadCreateTenant();
  return create(prefix ?? "regression");
}

export function apiContext(tenant: Tenant): { token: string; tenantId: string; base: string } {
  return { token: tenant.token, tenantId: tenant.tenantId, base: tenant.base };
}

export async function seedCustomer(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedCustomer(...args);
}

export async function seedBusinessServices(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedBusinessServices(...args);
}

export async function seedLead(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedLead(...args);
}

export async function seedScheduledJob(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedScheduledJob(...args);
}

export async function seedSentQuote(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedSentQuote(...args);
}

export async function seedCommunication(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.seedCommunication(...args);
}

export async function api(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.api(...args);
}

export async function apiRaw(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.apiRaw(...args);
}

export async function loginCustomer(...args: any[]): Promise<any> {
  const mod = await loadSeedHelpers();
  return mod.loginCustomer(...args);
}

async function resetAppState(page: Page): Promise<void> {
  await page.context().clearCookies();
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {
      // ignore
    }
  });
}

/**
 * Open the generic entry screen and choose a role card. The app opens on a
 * splash → role-select sequence ("I'm an Electrician" / "I'm a Customer"), so
 * every unauthenticated flow starts here.
 */
export async function gotoEntryRole(page: Page, role: "trade" | "customer"): Promise<void> {
  await resetAppState(page);
  await page.goto("/", { waitUntil: "networkidle" });
  await page
    .locator('[data-testid="role-select"]')
    .waitFor({ state: "visible", timeout: 120000 });
  await tap(page, role === "trade" ? "role-electrician" : "role-customer");
}

export async function loginAsTradeOwner(page: Page, tenant: Tenant): Promise<void> {
  await gotoEntryRole(page, "trade");
  await tap(page, "entry-trade-login");
  await waitText(page, "Electrician login");
  await fill(page, "login-email", tenant.adminEmail);
  await fill(page, "login-password", tenant.adminPassword);
  await tap(page, "login-submit");
  await waitText(page, "Dashboard", 30000);
  await settleAfterLogin();
}

export async function loginAsCustomer(
  page: Page,
  tenant: Tenant,
  credentials: LoginCredentials
): Promise<void> {
  await gotoEntryRole(page, "customer");
  await fillBusinessCode(page, tenant.code);
  await tap(page, "entry-find-business");
  await waitText(page, "Your electrician", 30000);
  await tap(page, "entry-customer-login");
  await waitText(page, "Customer login");
  await fill(page, "login-email", credentials.email);
  await fill(page, "login-password", credentials.password);
  await tap(page, "login-submit");
  // The customer home screen shows either the business name or "My quotes"
  // depending on whether branding loaded; wait for the primary action instead.
  await page.locator('[data-testid="request-new-quote"]').waitFor({ state: "visible", timeout: 30000 });
  await settleAfterLogin();
}

/**
 * Let the post-login screen transition finish before interacting.
 *
 * On CI (video encoding + runner CPU contention) the React Navigation
 * slide-in is still running when the landing screen's first elements become
 * visible; a tap fired mid-transition lands on the outgoing screen and is
 * dropped, which presented as the first post-login tap silently doing
 * nothing (N2/C12/F). Locally the transition completes fast enough to hide
 * this. The dashboard polls, so wait a fixed settle rather than networkidle.
 */
async function settleAfterLogin(): Promise<void> {
  await sleep(2000);
}

async function fillBusinessCode(page: Page, code: string): Promise<void> {
  const digits = code.replace(/\D/g, "").slice(0, 6);
  if (digits.length !== 6) {
    throw new Error(`Business code must be 6 digits, got "${code}"`);
  }
  const inputs = page.locator('[data-testid^="business-code-"]');
  await inputs.first().waitFor({ state: "visible", timeout: 20000 });
  for (let i = 0; i < 6; i++) {
    await page.locator(`[data-testid="business-code-${i}"]`).fill(digits[i]);
  }
}

export async function waitForLead(
  tenant: Tenant,
  title: string,
  timeout = 30000
): Promise<unknown> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const rows = await api(tenant, "/quote-requests");
    const found = rows.find(
      (r: any) =>
        r.title === title ||
        (r.structured_data && (r.structured_data.title === title || r.structured_data.category === title))
    );
    if (found) return found;
    await sleep(500);
  }
  throw new Error(`Lead "${title}" not found within ${timeout}ms`);
}

export async function waitForQuote(
  tenant: Tenant,
  title: string,
  status?: string,
  timeout = 30000
): Promise<unknown> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const rows = await api(tenant, "/quotes");
    const found = rows.find(
      (q: any) => q.title === title && (!status || q.status === status)
    );
    if (found) return found;
    await sleep(500);
  }
  throw new Error(`Quote "${title}"${status ? ` (${status})` : ""} not found within ${timeout}ms`);
}

export async function waitForJob(
  tenant: Tenant,
  title: string,
  status?: string,
  timeout = 30000
): Promise<unknown> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const rows = await api(tenant, "/jobs");
    const found = rows.find(
      (j: any) => j.title === title && (!status || j.status === status)
    );
    if (found) return found;
    await sleep(500);
  }
  throw new Error(`Job "${title}"${status ? ` (${status})` : ""} not found within ${timeout}ms`);
}

export async function waitForInvoice(
  tenant: Tenant,
  description: string,
  status?: string,
  timeout = 30000
): Promise<unknown> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const rows = await api(tenant, "/invoices");
    const found = rows.find(
      (inv: any) =>
        inv.line_items?.some((li: any) => li.description === description) &&
        (!status || inv.status === status)
    );
    if (found) return found;
    await sleep(500);
  }
  throw new Error(
    `Invoice with line "${description}"${status ? ` (${status})` : ""} not found within ${timeout}ms`
  );
}

export async function tap(page: Page, testId: string, settleMs = 400): Promise<void> {
  const visible = page.locator(`[data-testid="${testId}"]:visible`).first();
  const any = page.locator(`[data-testid="${testId}"]`).first();
  const locator = (await visible.count()) > 0 ? visible : any;
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

export async function tapText(page: Page, text: string, settleMs = 400): Promise<void> {
  const locator = page.getByText(text, { exact: false }).locator("visible=true").first();
  await locator.waitFor({ state: "visible", timeout: 20000 });
  await locator.click({ force: true });
  await sleep(settleMs);
}

export async function waitText(page: Page, text: string, timeout = 30000): Promise<void> {
  await page
    .getByText(text, { exact: false })
    .locator("visible=true")
    .first()
    .waitFor({ state: "visible", timeout });
}

export async function fill(page: Page, testId: string, value: string): Promise<void> {
  const input = page.locator(`[data-testid="${testId}"]`).locator("visible=true").first();
  await input.waitFor({ state: "visible", timeout: 20000 });
  await input.fill(value);
}

export async function bodyText(page: Page): Promise<string> {
  return page.locator("body").innerText();
}
