import { chromium, type FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? 'http://demo.localhost:3000';
  const email = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.local';
  const password = process.env.E2E_ADMIN_PASSWORD ?? 'password123';

  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });

  await page.goto('/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL('**/');

  await page.context().storageState({ path: 'playwright/.auth/admin.json' });
  await browser.close();
}

export default globalSetup;
