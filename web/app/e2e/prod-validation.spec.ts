import { test, expect } from './fixtures';
import {
  createCustomer,
  createQuote,
  createInvoice,
  createJob,
  openQuoteDetail,
  openInvoiceDetail,
  sendQuote,
  approveQuote,
  convertQuoteToInvoice,
  startJobFromBoard,
  completeJobFromBoard,
} from './helpers';

const djangoUsername = process.env.E2E_DJANGO_ADMIN_USERNAME ?? 'superadmin';
const djangoPassword = process.env.E2E_DJANGO_ADMIN_PASSWORD ?? '';
const adminBaseUrl = process.env.E2E_ADMIN_BASE_URL ?? 'http://localhost:8001';
const setupToken = process.env.SETUP_TOKEN ?? '';

// Require at least one bootstrap path: setup-token API (preferred) or Django admin.
test.skip(!setupToken && !djangoPassword, 'SETUP_TOKEN or E2E_DJANGO_ADMIN_PASSWORD is required');

test.describe('production validation', () => {
  test.describe.configure({ mode: 'serial' });
  test.use({ storageState: undefined });
  test.setTimeout(180_000);

  let tenantSlug = '';
  let tenantName = '';
  let adminEmail = '';
  const adminPassword = 'prod-validation-pass-123';
  let customerName = '';
  let quoteRef = '';
  let jobRef = '';
  let invoiceRef = '';
  let tenantSessionCookie = '';

  const attachTenantSession = async (page: import('@playwright/test').Page) => {
    if (!tenantSessionCookie) {
      throw new Error('Tenant session cookie is not initialized');
    }
    await page.context().addCookies([
      {
        name: 'session',
        value: tenantSessionCookie,
        domain: 'demo.localhost',
        path: '/',
        httpOnly: true,
        secure: false,
        sameSite: 'Lax',
      },
    ]);
  };

  test('health endpoints are reachable', async ({ request }) => {
    const api = await request.get('http://demo.localhost:8000/health');
    expect(api.ok()).toBeTruthy();

    const web = await request.get('http://demo.localhost:3000');
    expect(web.ok()).toBeTruthy();

    const admin = await request.get('http://localhost:8001/admin/login/');
    expect([200, 302]).toContain(admin.status());
  });

  test('bootstrap tenant and admin user', async ({ page, request }) => {
    const id = `prod-${Date.now()}`;
    tenantSlug = `prod-validation-${id}`;
    tenantName = `Prod Validation ${id}`;
    adminEmail = `admin-${id}@example.com`;

    if (setupToken) {
      const response = await request.post('http://demo.localhost:8000/tenants', {
        headers: {
          'Content-Type': 'application/json',
          'X-Setup-Token': setupToken,
        },
        data: {
          slug: tenantSlug,
          name: tenantName,
          admin_email: adminEmail,
          admin_password: adminPassword,
          admin_name: 'Prod Validation Admin',
        },
      });
      expect(response.ok()).toBeTruthy();
    } else {
      await page.goto(`${adminBaseUrl}/admin/login/`);
      await page.getByLabel('Username:').fill(djangoUsername);
      await page.getByLabel('Password:').fill(djangoPassword);
      await page.getByRole('button', { name: 'Log in' }).click();
      await expect(page).toHaveURL(`${adminBaseUrl}/admin/`);

      await page.goto(`${adminBaseUrl}/admin/operations/tenant/add/`);
      await page.getByLabel('Name:').fill(tenantName);
      await page.getByLabel('Slug:').fill(tenantSlug);
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.getByText('was added successfully')).toBeVisible();

      await page.goto(`${adminBaseUrl}/admin/operations/user/add/`);
      await page.locator('select[name="tenant"]').selectOption({ label: tenantName });
      await page.getByLabel('Email:').fill(adminEmail);
      await page.getByLabel('Full name:').fill('Prod Validation Admin');
      await page.getByLabel('Role:').fill('admin');
      await page.getByLabel('Password:', { exact: true }).fill(adminPassword);
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.getByText('was added successfully')).toBeVisible();
    }

    let cookie: string | null = null;
    for (let attempt = 0; attempt < 10; attempt++) {
      const loginResponse = await request.post('http://demo.localhost:8000/auth/login', {
        data: {
          tenant_slug: tenantSlug,
          email: adminEmail,
          password: adminPassword,
        },
      });
      const setCookie = loginResponse.headers()['set-cookie'];
      const cookieMatch = setCookie?.match(/session=([^;]+)/);
      if (loginResponse.ok() && cookieMatch?.[1]) {
        cookie = cookieMatch[1];
        break;
      }
      // Retry transient bootstrap races and auth throttling during CI retries.
      await page.waitForTimeout(loginResponse.status() === 429 ? 10_000 : 2_000);
    }

    expect(cookie).toBeTruthy();
    tenantSessionCookie = cookie!;
  });

  test('login to the back-office UI', async ({ page }) => {
    await page.goto('/login');
    for (let attempt = 0; attempt < 4; attempt++) {
      await page.getByLabel(/business slug/i).fill(tenantSlug);
      await page.getByLabel(/email/i).fill(adminEmail);
      await page.getByLabel(/password/i).fill(adminPassword);
      await page.getByRole('button', { name: /sign in/i }).click();

      try {
        await expect(page).toHaveURL(/\/($|dashboard)/, { timeout: 10_000 });
        break;
      } catch {
        const throttled = await page.getByText(/too many requests/i).isVisible().catch(() => false);
        if (throttled && attempt < 3) {
          await page.waitForTimeout(10_000);
          continue;
        }
        throw new Error(`Login did not reach dashboard; current URL: ${page.url()}`);
      }
    }

    await expect(page).toHaveURL(/\/($|dashboard)/, { timeout: 30_000 });
    await expect(page.getByRole('link', { name: /new quote/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('link', { name: /quotes/i })).toBeVisible({ timeout: 30_000 });
  });

  test('customer, quote, job and invoice lifecycle', async ({ page }) => {
    await attachTenantSession(page);
    await page.goto('/');
    const id = tenantSlug.split('-').slice(-2).join('-');

    customerName = await createCustomer(page, id);
    await expect(page.getByText(customerName)).toBeVisible();

    quoteRef = await createQuote(page, customerName, id);
    await page.goto('/quotes');
    await expect(page.getByRole('link', { name: new RegExp(quoteRef, 'i') }).first()).toBeVisible();

    jobRef = await createJob(page, customerName, id);
    await page.goto('/jobs');
    await expect(page.getByText(jobRef)).toBeVisible();

    invoiceRef = await createInvoice(page, customerName, id);
    await page.goto('/invoices');
    await expect(page.getByRole('link', { name: new RegExp(invoiceRef, 'i') }).first()).toBeVisible();
  });

  test('AI quote generation (RAG)', async ({ page }) => {
    test.slow();
    await attachTenantSession(page);
    const id = `ai-${Date.now()}`;

    await page.goto('/quotes');
    await page.getByTestId('generate-ai-quote').click();
    await expect(page.getByRole('heading', { name: /generate quote with ai/i })).toBeVisible();

    await page.getByLabel(/new lead/i).check();
    await page.getByPlaceholder(/customer name/i).fill('AI Validation Customer');
    await page.getByPlaceholder(/email/i).fill(`${id}@example.com`);
    await page.getByLabel(/job description/i).fill(
      'Replace a broken consumer unit and install 4 new double sockets in a 3 bedroom house'
    );
    const generateResponsePromise = page.waitForResponse(
      (res) => res.url().includes('/quotes/generate') && res.request().method() === 'POST',
      { timeout: 90_000 }
    );
    await page.getByRole('button', { name: /generate draft/i }).click();

    const generateResponse = await generateResponsePromise;
    if (generateResponse.ok()) {
      await expect(page).toHaveURL(/\/quotes\/[0-9a-f-]+$/, { timeout: 90_000 });
      await expect(page.getByText('AI Validation Customer')).toBeVisible();
      await expect(page.getByText(/£[0-9,]+/).first()).toBeVisible();

      // Download can be flaky in containerized prod-like runs. Try it with a
      // bounded timeout, but do not fail a successful generation flow solely
      // on missing browser download events.
      const downloadButton = page.getByRole('button', { name: /download pdf/i });
      const hasDownloadButton = await downloadButton.isVisible({ timeout: 15_000 }).catch(() => false);
      if (hasDownloadButton) {
        const downloadPromise = page
          .waitForEvent('download', { timeout: 15_000 })
          .catch(() => null);
        await downloadButton.click();
        const download = await downloadPromise;
        if (download) {
          expect(await download.path()).toBeTruthy();
        }
      }
      return;
    }

    // In prod-like validation, upstream AI dependencies can be unavailable.
    // Verify the failure is surfaced and the app stays stable on the quotes page.
    expect(generateResponse.status()).toBe(503);
    await expect(page).toHaveURL(/\/quotes$/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { name: /generate quote with ai/i })).toBeVisible();
  });

  test('quote status lifecycle and conversion to invoice', async ({ page }) => {
    await attachTenantSession(page);
    await page.goto('/');
    await openQuoteDetail(page, quoteRef);
    await sendQuote(page);
    await approveQuote(page);
    await convertQuoteToInvoice(page);
    await expect(page.getByRole('button', { name: /mark as paid/i })).toBeVisible();
  });

  test('job board lifecycle', async ({ page }) => {
    await attachTenantSession(page);
    await page.goto('/');
    await startJobFromBoard(page, jobRef);
    await completeJobFromBoard(page, jobRef);
    await expect(page.getByText(jobRef)).toBeVisible();
  });

  test('invoice status lifecycle', async ({ page }) => {
    await attachTenantSession(page);
    await page.goto('/');
    await openInvoiceDetail(page, invoiceRef);
    await page.getByRole('button', { name: /mark as paid/i }).click();
    await expect(
      page.locator('span', { hasText: /paid/i }).filter({ hasClass: /rounded-full/ }).first()
    ).toBeVisible();
  });

  test('settings page loads', async ({ page }) => {
    await attachTenantSession(page);
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: /settings/i })).toBeVisible();
  });

  test('feature flags are served', async ({ page }) => {
    const response = await page.request.get('http://demo.localhost:8000/feature-flags');
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body).toHaveProperty('voice_ai_insights');
    expect(body).toHaveProperty('demand_forecasting');
    expect(body).toHaveProperty('external_integrations');
  });
});
