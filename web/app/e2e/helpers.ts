import type { Page } from '@playwright/test';

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function openDetailByReference(page: Page, path: string, reference: string): Promise<void> {
  const link = page.getByRole('link', { name: new RegExp(escapeRegExp(reference), 'i') }).first();
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(path);
    try {
      await link.waitFor({ state: 'visible', timeout: 10_000 });
      await link.click();
      return;
    } catch {
      // Retry once the list has had an extra render cycle.
    }
  }
  await link.waitFor({ state: 'visible', timeout: 30_000 });
  await link.click();
}

async function waitForJobInColumn(page: Page, reference: string, column: string): Promise<void> {
  const card = jobCardInColumn(page, reference, column);
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await card.waitFor({ state: 'visible', timeout: 10_000 });
      return;
    } catch {
      await page.goto('/jobs');
    }
  }
  await card.waitFor({ state: 'visible', timeout: 30_000 });
}

export async function loginAsDefaultAdmin(page: Page): Promise<void> {
  const tenantSlug = process.env.E2E_TENANT_SLUG ?? 'demo';
  const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.example.com';
  const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-password-123';

  await page.goto('/login');
  await page.getByLabel(/business slug/i).fill(tenantSlug);
  await page.getByLabel(/email/i).fill(adminEmail);
  await page.getByLabel(/password/i).fill(adminPassword);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL(/\/($|dashboard)/, { timeout: 30_000 });
}

async function recoverIfOnLogin(page: Page): Promise<void> {
  const pathname = new URL(page.url()).pathname;
  const onLoginPath = pathname.startsWith('/login');
  const hasSignInForm = await page
    .getByRole('button', { name: /sign in/i })
    .isVisible()
    .catch(() => false);

  if (!onLoginPath && !hasSignInForm) {
    return;
  }

  await ensureDefaultAdminSession(page);
}

export async function ensureDefaultAdminSession(page: Page): Promise<void> {
  const tenantSlug = process.env.E2E_TENANT_SLUG ?? 'demo';
  const adminEmail = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.example.com';
  const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-password-123';
  const apiBaseUrl = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8000';

  let sessionCookie: string | null = null;
  for (let attempt = 0; attempt < 10; attempt++) {
    try {
      const response = await page.request.post(`${apiBaseUrl}/auth/login`, {
        data: {
          tenant_slug: tenantSlug,
          email: adminEmail,
          password: adminPassword,
        },
      });
      const setCookie = response.headers()['set-cookie'];
      const cookieMatch = setCookie?.match(/session=([^;]+)/);
      if (response.ok() && cookieMatch?.[1]) {
        sessionCookie = cookieMatch[1];
        break;
      }
      await sleep(response.status() === 429 ? 10_000 : 2_000);
    } catch {
      await sleep(2_000);
    }
  }

  if (!sessionCookie) {
    throw new Error('Failed to establish default admin session for E2E');
  }

  // Prevent host-only and domain cookie collisions from stale storage state.
  await page.context().clearCookies();
  await page.context().addCookies([
    {
      name: 'session',
      value: sessionCookie,
      domain: 'demo.localhost',
      path: '/',
      httpOnly: true,
      secure: false,
      sameSite: 'Lax',
    },
  ]);

  await page.goto('/');
  if (!/\/($|dashboard)/.test(page.url())) {
    throw new Error(`Default admin session did not land on app shell, current URL: ${page.url()}`);
  }
}

export async function createCustomer(
  page: Page,
  testId: string,
  overrides: { firstName?: string; lastName?: string; phone?: string } = {}
): Promise<string> {
  const firstName = overrides.firstName ?? `E2E`;
  const lastName = overrides.lastName ?? `Customer-${testId}`;
  const customerName = `${firstName} ${lastName}`;

  const addCustomerButton = page.getByRole('button', { name: /add customer/i });
  for (let attempt = 0; attempt < 5; attempt++) {
    await page.goto('/customers');
    await recoverIfOnLogin(page);
    try {
      await page.waitForURL(/\/customers$/, { timeout: 10_000 });
    } catch {
      // Occasionally the app shell lands on the dashboard first; force route again.
      await page.goto('/customers');
      await page.waitForURL(/\/customers$/, { timeout: 10_000 });
    }

    try {
      await addCustomerButton.waitFor({ state: 'visible', timeout: 10_000 });
      await addCustomerButton.click();
      break;
    } catch {
      await recoverIfOnLogin(page);
      if (attempt === 4) {
        throw new Error(`Add customer button did not become available; current URL: ${page.url()}`);
      }
    }
  }

  await page.getByPlaceholder(/first name/i).fill(firstName);
  await page.getByPlaceholder(/last name/i).fill(lastName);
  await page.getByPlaceholder(/email/i).fill(`e2e-${testId}@demo.local`);
  await page.getByPlaceholder(/phone/i).fill(overrides.phone ?? '07700 000000');
  await page.getByPlaceholder(/address/i).fill('1 Test Road');
  await page.getByPlaceholder(/postcode/i).fill('TE1 1ST');

  await page.getByRole('button', { name: /save customer/i }).click();
  await page.locator('.rounded-xl', { hasText: customerName }).first().waitFor({ timeout: 30_000 });

  return customerName;
}

export async function createQuote(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `QUOTE-${testId}`;

  await page.goto('/quotes');
  await page.getByRole('button', { name: /new quote/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create quote/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.getByPlaceholder(/service type/i).fill('Consumer unit replacement');
  await modal.getByPlaceholder(/property address/i).fill('1 Test Road, TE1 1ST');
  await modal.getByPlaceholder(/description/i).fill('Labour and materials');
  await modal.locator('input[type="number"]').nth(1).fill('250');

  await modal.getByRole('button', { name: /create quote/i }).click();
  await page.getByRole('link', { name: new RegExp(escapeRegExp(reference), 'i') }).first().waitFor({ timeout: 30_000 });

  return reference;
}

export async function openQuoteDetail(page: Page, reference: string) {
  await openDetailByReference(page, '/quotes', reference);
  await page.waitForURL(/\/quotes\/[0-9a-f-]+$/);
}

export async function sendQuote(page: Page) {
  await page.getByRole('button', { name: /send to customer/i }).click();
  await page.getByRole('button', { name: /approve quote/i }).waitFor();
}

export async function approveQuote(page: Page) {
  await page.getByRole('button', { name: /approve quote/i }).click();
  await page.getByRole('button', { name: /convert to invoice/i }).waitFor();
}

export async function convertQuoteToInvoice(page: Page) {
  await page.getByRole('button', { name: /convert to invoice/i }).click();
  await page.waitForURL(/\/invoices\/[0-9a-f-]+$/);
}

export async function createJob(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `JOB-${testId}`;

  await page.goto('/jobs');
  await page.getByRole('button', { name: /new job/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create job/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.getByPlaceholder(/service type/i).fill('Consumer unit replacement');
  await modal.locator('input[type="date"]').fill(new Date().toISOString().split('T')[0]);
  await modal.getByPlaceholder(/property address/i).fill('1 Test Road, TE1 1ST');
  await modal.getByPlaceholder(/value/i).fill('500');
  await modal.getByPlaceholder(/description/i).fill('Scheduled installation work');

  await modal.getByRole('button', { name: /create job/i }).click();
  await waitForJobInColumn(page, reference, 'Scheduled');

  return reference;
}

function jobCardInColumn(page: Page, reference: string, column: string) {
  return page
    .locator('div.rounded-xl.border', { has: page.locator('span', { hasText: new RegExp(`^${column}$`) }) })
    .locator('div.rounded-lg', { hasText: reference })
    .first();
}

export async function startJobFromBoard(page: Page, reference: string) {
  await page.goto('/jobs');
  const card = jobCardInColumn(page, reference, 'Scheduled');
  await card.getByRole('button', { name: /start/i }).click();
  await waitForJobInColumn(page, reference, 'In Progress');
}

export async function completeJobFromBoard(page: Page, reference: string) {
  await page.goto('/jobs');
  const card = jobCardInColumn(page, reference, 'In Progress');
  await card.getByRole('button', { name: /complete/i }).click();
  await waitForJobInColumn(page, reference, 'Completed');
}

export async function createInvoice(
  page: Page,
  customerName: string,
  testId: string,
): Promise<string> {
  const reference = `INV-${testId}`;
  const today = new Date().toISOString().split('T')[0];
  const dueDate = new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  await page.goto('/invoices');
  await page.getByRole('button', { name: /create invoice/i }).click();

  const modal = page.locator('div.fixed.inset-0').filter({ has: page.getByRole('button', { name: /create invoice/i }) });
  await modal.locator('select').first().selectOption({ label: customerName });
  await modal.getByPlaceholder(/reference/i).fill(reference);
  await modal.locator('input[type="date"]').first().fill(today);
  await modal.locator('input[type="date"]').nth(1).fill(dueDate);
  await modal.getByPlaceholder(/description/i).fill('Labour and materials');
  await modal.locator('input[type="number"]').nth(1).fill('300');

  await modal.getByRole('button', { name: /create invoice/i }).click();
  await page.getByRole('link', { name: new RegExp(escapeRegExp(reference), 'i') }).first().waitFor({ timeout: 30_000 });

  return reference;
}

export async function openInvoiceDetail(page: Page, reference: string) {
  await openDetailByReference(page, '/invoices', reference);
  await page.waitForURL(/\/invoices\/[0-9a-f-]+$/);
}

export async function sendInvoice(page: Page) {
  await page.getByRole('button', { name: /send reminder/i }).click();
  await expectStatusPill(page, /sent/i);
}

export async function markInvoicePaid(page: Page) {
  await page.getByRole('button', { name: /mark as paid/i }).click();
  await expectStatusPill(page, /paid/i);
}

async function expectStatusPill(page: Page, pattern: RegExp) {
  await page.locator('span', { hasText: pattern }).filter({ hasClass: /rounded-full/ }).first().waitFor();
}
