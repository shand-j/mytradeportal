import { chromium, type FullConfig } from '@playwright/test';

async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? process.env.E2E_BASE_URL ?? 'http://demo.localhost:3000';
  const parsedBase = new URL(baseURL);
  const apiBaseURL = process.env.E2E_API_BASE_URL
    ?? (parsedBase.hostname.startsWith('web-') && parsedBase.hostname.endsWith('.up.railway.app')
      ? `${parsedBase.protocol}//${parsedBase.hostname.replace(/^web-/, 'api-')}`
      : `http://${parsedBase.hostname}:8000`);
  const appHost = new URL(baseURL).hostname;
  const email = process.env.E2E_ADMIN_EMAIL ?? 'admin@demo.example.com';
  const password = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-password-123';
  const tenantSlug = process.env.E2E_TENANT_SLUG ?? 'demo';

  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });

  let loginError = 'Unknown login error';
  let loginSucceeded = false;
  for (let attempt = 0; attempt < 30; attempt++) {
    try {
      const loginResponse = await page.request.post(`${apiBaseURL}/auth/login`, {
        data: {
          tenant_slug: tenantSlug,
          email,
          password,
        },
      });
      if (loginResponse.ok()) {
        const setCookie = loginResponse.headers()['set-cookie'];
        const token = setCookie?.match(/session=([^;]+)/)?.[1];
        if (token) {
          await page.context().addCookies([
            {
              name: 'session',
              value: token,
              domain: appHost,
              path: '/',
              httpOnly: true,
              secure: false,
              sameSite: 'Lax',
            },
          ]);
        }
        loginSucceeded = true;
        break;
      }
      loginError = `HTTP ${loginResponse.status()}: ${await loginResponse.text()}`;
    } catch (error) {
      loginError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  if (!loginSucceeded) {
    throw new Error(`Playwright global setup login failed after retries: ${loginError}`);
  }

  await page.goto('/');
  await page.waitForURL('**/');

  await page.context().storageState({ path: 'playwright/.auth/admin.json' });
  await browser.close();
}

export default globalSetup;
