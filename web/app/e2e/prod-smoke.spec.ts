import { test, expect } from './fixtures';
import {
  createCustomer,
  createQuote,
  createInvoice,
  createJob,
} from './helpers';

const djangoUsername = process.env.E2E_DJANGO_ADMIN_USERNAME ?? 'superadmin';
const djangoPassword = process.env.E2E_DJANGO_ADMIN_PASSWORD ?? '';
const adminBaseUrl = process.env.E2E_ADMIN_BASE_URL ?? 'http://localhost:8001';
const webBaseUrl = process.env.E2E_BASE_URL ?? 'http://demo.localhost:3000';
const setupToken = process.env.SETUP_TOKEN ?? '';

function resolveSmokeApiBaseUrl(): string {
  const explicit = process.env.E2E_API_BASE_URL;
  if (explicit && explicit !== '') {
    return explicit;
  }

  try {
    const parsed = new URL(webBaseUrl);
    if (parsed.hostname.startsWith('web-') && parsed.hostname.endsWith('.up.railway.app')) {
      return `${parsed.protocol}//${parsed.hostname.replace(/^web-/, 'api-')}`;
    }
    return `http://${parsed.hostname}:8000`;
  } catch {
    return 'http://127.0.0.1:8000';
  }
}

const smokeApiBaseUrl = resolveSmokeApiBaseUrl();

// Require at least one bootstrap path: setup-token API (preferred) or Django admin.
test.skip(!setupToken && !djangoPassword, 'SETUP_TOKEN or E2E_DJANGO_ADMIN_PASSWORD is required');

test.describe('production smoke test', () => {
  test.use({ storageState: undefined });

  let tenantSlug = '';
  let tenantName = '';
  let adminEmail = '';
  const adminPassword = 'smoke-admin-pass-123';

  test.beforeEach(async ({ page, request }) => {
    const id = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    tenantSlug = `prod-smoke-${id}`;
    tenantName = `Prod Smoke ${id}`;
    adminEmail = `admin-${id}@example.com`;

    if (setupToken) {
      const response = await request.post(`${smokeApiBaseUrl}/tenants`, {
        headers: {
          'Content-Type': 'application/json',
          'X-Setup-Token': setupToken,
        },
        data: {
          slug: tenantSlug,
          name: tenantName,
          admin_email: adminEmail,
          admin_password: adminPassword,
          admin_name: 'Smoke Test Admin',
        },
      });
      expect(response.ok()).toBeTruthy();
    } else {
      // Fallback path for environments without setup token access.
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
      await page.getByLabel('Full name:').fill('Smoke Test Admin');
      await page.getByLabel('Role:').fill('admin');
      await page.getByLabel('Password:', { exact: true }).fill(adminPassword);
      await page.getByRole('button', { name: 'Save', exact: true }).click();
      await expect(page.getByText('was added successfully')).toBeVisible();
    }

    // Persist the tenant slug so teardown can clean it up.
    process.env.E2E_SMOKE_TENANT_SLUG = tenantSlug;
    // Also write it to disk for CI teardown steps that run in a separate process.
    const fs = await import('fs');
    const path = await import('path');
    const tmpDir = process.env.E2E_ARTIFACT_DIR ?? 'playwright/.tmp';
    fs.mkdirSync(tmpDir, { recursive: true });
    fs.writeFileSync(path.join(tmpDir, 'prod-smoke-tenant.json'), JSON.stringify({ tenantSlug, tenantName, adminEmail }));
  });

  test('smoke: customer, quote, invoice and job', async ({ page }) => {
    test.setTimeout(90_000); // allow slower prod env just for this smoke flow

    // 5. Log in to the back-office UI as the new tenant admin.
    await page.goto('/login');
    await page.getByLabel(/business slug/i).fill(tenantSlug);
    await page.getByLabel(/email/i).fill(adminEmail);
    await page.getByLabel(/password/i).fill(adminPassword);

    await page.getByRole('button', { name: /sign in/i }).click();

    // Use route + shell controls as stable logged-in signals.
    await expect(page).toHaveURL(/\/($|dashboard)/, { timeout: 30_000 });
    await expect(page.getByRole('link', { name: /new quote/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('link', { name: /quotes/i })).toBeVisible({ timeout: 30_000 });

    // 6. Exercise core functionality.
    const customerName = await createCustomer(page, tenantSlug);

    const quoteRef = await createQuote(page, customerName, tenantSlug);
    await page.goto('/quotes');
    await expect(page.getByRole('link', { name: new RegExp(quoteRef, 'i') }).first()).toBeVisible();

    const invoiceRef = await createInvoice(page, customerName, tenantSlug);
    await page.goto('/invoices');
    await expect(page.getByRole('link', { name: new RegExp(invoiceRef, 'i') }).first()).toBeVisible();

    const jobRef = await createJob(page, customerName, tenantSlug);
    await page.goto('/jobs');
    await expect(page.getByText(jobRef)).toBeVisible();
  });
});
