#!/usr/bin/env node
/**
 * capture-screenshots.mjs — visual record sweep for go-live review.
 *
 * Captures full-page screenshots of every page / major component state in both
 * apps (web back-office on :3000, mobile Expo web build on :8090) into
 * docs/screenshots/{web,mobile}/*.png, plus a capture-report.json with
 * per-shot console errors and failures.
 *
 * Usage:
 *   node scripts/capture-screenshots.mjs            # both apps
 *   node scripts/capture-screenshots.mjs web        # web only
 *   node scripts/capture-screenshots.mjs mobile     # mobile only
 *
 * Requires: stack up (api :8000, web :3000) and Expo web dev server on :8090
 *   cd mobile && EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm exec expo start --web --port 8090
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../web/app/package.json'),
);
const { chromium } = require('@playwright/test');

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const WEB_BASE = process.env.WEB_BASE_URL || 'http://localhost:3000';
const MOBILE_BASE = process.env.MOBILE_BASE_URL || 'http://localhost:8090';
const OUT_WEB = path.join(ROOT, 'docs/screenshots/web');
const OUT_MOBILE = path.join(ROOT, 'docs/screenshots/mobile');

// Seeded demo estate (tenant `sparks`) — see docs/testing-accounts.md.
const CREDS = {
  slug: 'sparks',
  staffEmail: 'sam@sparksandsons.co.uk',
  customerEmail: 'margaret.holloway@example.co.uk',
  password: 'GoLive2026!',
};
const IDS = {
  quoteAiDraft: '79571042-f90a-4754-979a-bc1f2e7bce26', // Consumer unit replacement (AI draft, conf 0.87)
  quoteAiSent: 'a8b3ebe7-3f3b-4800-acf3-d1b1667c3c86', // Kitchen downlights (AI, sent)
  jobInProgress: 'af2e729d-07b0-479f-99bf-7bdd7d2c66be',
  customer: '451a971f-2aeb-4656-b905-0b794503af5d', // Margaret Holloway (web /contacts id)
  invoiceDraft: 'eef6c2d6-90b6-4466-9a26-c4d4a635290b',
  invoicePaid: '9b0d5d56-5c2c-4161-b46e-1b4550e10a4d',
  leadProcessed: '2add2b54-0740-4d6e-a511-fd2f6f0d57ea', // triage thread (customer <-> AI)
  leadConverted: '04626018-3208-47eb-8619-d7c161ccc935', // Margaret's, linked to AI draft
};

const report = { web: [], mobile: [], failures: [] };

function attachConsoleCollector(page, bucket) {
  page.on('console', (msg) => {
    if (msg.type() === 'error') bucket.push(msg.text().slice(0, 500));
  });
  page.on('pageerror', (err) => bucket.push(`pageerror: ${String(err).slice(0, 500)}`));
}

async function snap(page, outDir, name, { fullPage = true, scrollTo = null } = {}) {
  const errors = [];
  const file = path.join(outDir, `${name}.png`);
  try {
    if (scrollTo) {
      const loc = page.locator(scrollTo).first();
      await loc.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(600);
    }
    await page.screenshot({ path: file, fullPage });
    return { name, ok: true, file: path.relative(ROOT, file) };
  } catch (err) {
    report.failures.push({ name, error: String(err).slice(0, 300) });
    return { name, ok: false, error: String(err).slice(0, 300) };
  }
}

async function gotoAndSettle(page, url, { first = false, settleMs = 2500 } = {}) {
  await page.goto(url, {
    waitUntil: 'domcontentloaded',
    timeout: first ? 120000 : 45000,
  });
  // Vite/Expo dev servers keep websockets open, so networkidle is unreliable —
  // use a fixed settle delay instead.
  await page.waitForTimeout(first ? 12000 : settleMs);
}

// ---------------------------------------------------------------- web sweep
async function captureWeb(browser) {
  const consoleErrors = {};
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  attachConsoleCollector(page, (consoleErrors.__all = []));

  // Login page, then log in as the Sparks & Sons owner.
  await gotoAndSettle(page, `${WEB_BASE}/login`, { first: true, settleMs: 3000 });
  report.web.push(await snap(page, OUT_WEB, 'login'));

  await page.fill('#tenantSlug', CREDS.slug);
  await page.fill('#email', CREDS.staffEmail);
  await page.fill('#password', CREDS.password);
  await page.locator('form button[type=submit], form button').first().click();
  await page.waitForURL(`${WEB_BASE}/`, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(3000);
  if (!page.url().endsWith('/')) {
    report.failures.push({ name: 'web-login', error: `login did not reach dashboard, url=${page.url()}` });
    await snap(page, OUT_WEB, 'login-failed');
    await context.close();
    return;
  }
  report.web.push(await snap(page, OUT_WEB, 'dashboard'));

  const routes = [
    ['calendar-month', '/calendar'],
    ['calendar-week', '/calendar/week'],
    ['calendar-day', '/calendar/day'],
    ['quotes-list', '/quotes'],
    ['jobs-board', '/jobs'],
    ['job-detail', `/jobs/${IDS.jobInProgress}`],
    ['customers-list', '/customers'],
    ['customer-detail', `/customers/${IDS.customer}`],
    ['invoices-list', '/invoices'],
    ['invoice-detail-paid', `/invoices/${IDS.invoicePaid}`],
    ['invoice-detail-draft', `/invoices/${IDS.invoiceDraft}`],
    ['reviews', '/reviews'],
    ['ai-insights', '/ai-insights'],
  ];
  for (const [name, route] of routes) {
    await gotoAndSettle(page, `${WEB_BASE}${route}`);
    report.web.push(await snap(page, OUT_WEB, name));
  }

  // AI quote detail (full page) + "Refine with AI" section.
  await gotoAndSettle(page, `${WEB_BASE}/quotes/${IDS.quoteAiDraft}`);
  report.web.push(await snap(page, OUT_WEB, 'quote-detail-ai'));
  report.web.push(
    await snap(page, OUT_WEB, 'quote-detail-ai-refine', {
      fullPage: false,
      scrollTo: '#refine-instructions',
    }),
  );
  // Second AI quote (sent, manually edited afterwards).
  await gotoAndSettle(page, `${WEB_BASE}/quotes/${IDS.quoteAiSent}`);
  report.web.push(await snap(page, OUT_WEB, 'quote-detail-ai-sent'));

  // "Generate with AI" dialog on the quotes list.
  await gotoAndSettle(page, `${WEB_BASE}/quotes`);
  const genBtn = page.locator('[data-testid="generate-ai-quote"]');
  if (await genBtn.count()) {
    await genBtn.first().click();
    await page.waitForTimeout(1200);
    report.web.push(await snap(page, OUT_WEB, 'quotes-generate-ai-dialog', { fullPage: false }));
    await page.keyboard.press('Escape');
  } else {
    report.failures.push({ name: 'quotes-generate-ai-dialog', error: 'button not found' });
  }

  // Settings tabs (client-side state; the /settings/:tab param is ignored by the page).
  await gotoAndSettle(page, `${WEB_BASE}/settings`);
  report.web.push(await snap(page, OUT_WEB, 'settings-business'));
  for (const tab of ['Branding', 'Services', 'Integrations']) {
    const btn = page.getByRole('button', { name: tab, exact: true });
    if (await btn.count()) {
      await btn.first().click();
      await page.waitForTimeout(1200);
      report.web.push(await snap(page, OUT_WEB, `settings-${tab.toLowerCase()}`));
    } else {
      report.failures.push({ name: `settings-${tab.toLowerCase()}`, error: 'tab button not found (feature-flagged?)' });
    }
  }

  fs.writeFileSync(
    path.join(ROOT, 'docs/screenshots/web-console-errors.json'),
    JSON.stringify(consoleErrors.__all, null, 2),
  );
  await context.close();
}

// ------------------------------------------------------------- mobile sweep
async function mobileLogin(page, { role, email }) {
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder('Password').fill(CREDS.password);
  await page.locator('[data-testid="login-submit"]').click();
  await page.waitForTimeout(9000); // login + tenant/theme fetch
}

// The entry screen gates on a tenant lookup; type the seeded 6-digit code so
// businessStore.business is set (customer login requires the slug). The code
// must be entered in the SAME page session as the login: businessStore is
// in-memory Zustand state, so a full-page navigation (page.goto) drops it.
// Returns the page positioned wherever the code lookup landed.
async function loadBusinessViaCode(page) {
  await gotoAndSettle(page, `${MOBILE_BASE}/`, { settleMs: 4000 });
  const codeInput = page.locator('input').first();
  await codeInput.click();
  await page.keyboard.type(process.env.TENANT_CODE || '455160', { delay: 80 });
  await page.waitForTimeout(800);
  const findBtn = page.getByText('Find my electrician');
  if (await findBtn.count()) {
    await findBtn.first().click();
    await page.waitForTimeout(4000);
  }
}

async function captureMobile() {
  const consoleErrors = {};
  // The local API only allows the http://localhost:3000 origin (CORS), and the
  // Expo web build on :8090 is not whitelisted. The shipped mobile app is
  // native (no CORS), so for capture we relax web security in the browser only.
  const browser = await chromium.launch({ args: ['--disable-web-security'] });
  const newMobileContext = () =>
    browser.newContext({ viewport: { width: 402, height: 874 }, deviceScaleFactor: 2 });

  // --- unauthenticated entry screens (fresh context) ---
  {
    const context = await newMobileContext();
    const page = await context.newPage();
    attachConsoleCollector(page, (consoleErrors.entry = []));
    await gotoAndSettle(page, `${MOBILE_BASE}/`, { first: true });
    report.mobile.push(await snap(page, OUT_MOBILE, 'entry'));
    await gotoAndSettle(page, `${MOBILE_BASE}/trade-login`, { settleMs: 3500 });
    report.mobile.push(await snap(page, OUT_MOBILE, 'trade-login'));
    await gotoAndSettle(page, `${MOBILE_BASE}/customer-login`, { settleMs: 3500 });
    report.mobile.push(await snap(page, OUT_MOBILE, 'customer-login'));
    await context.close();
  }

  // --- trade session ---
  {
    const context = await newMobileContext();
    const page = await context.newPage();
    attachConsoleCollector(page, (consoleErrors.trade = []));
    await gotoAndSettle(page, `${MOBILE_BASE}/trade-login`, { first: true, settleMs: 4000 });
    await mobileLogin(page, { role: 'trade', email: CREDS.staffEmail });
    if (!/dashboard|\(trade\)/.test(page.url())) {
      // Known defect: successful trade login does not navigate away from
      // /trade-login (LoginScreen has no onSuccess navigation), so go to the
      // dashboard explicitly for the capture.
      report.failures.push({ name: 'mobile-trade-login', error: `no redirect after login, url=${page.url()}` });
    }
    await gotoAndSettle(page, `${MOBILE_BASE}/(trade)/dashboard`, { settleMs: 4000 });
    report.mobile.push(await snap(page, OUT_MOBILE, 'trade-dashboard'));

    const tradeRoutes = [
      ['trade-quotes', '/(trade)/quotes'],
      ['trade-leads', '/(trade)/leads'],
      ['trade-lead-detail-triage', `/(trade)/lead/${IDS.leadProcessed}`],
      ['trade-request-info-chat', `/(trade)/request-info?leadId=${IDS.leadProcessed}`],
      ['trade-messages-thread', `/(trade)/messages?quoteRequestId=${IDS.leadProcessed}`],
      ['trade-quote-review-ai', `/(trade)/quote/${IDS.quoteAiDraft}`],
      ['trade-quote-intake', `/(trade)/quote-intake?leadId=${IDS.leadProcessed}`],
      ['trade-customers', '/(trade)/customers'],
      ['trade-calendar-week', '/(trade)/calendar'],
      ['trade-invoices', '/(trade)/invoices'],
      ['trade-invoice-detail-paid', `/(trade)/invoice/${IDS.invoicePaid}`],
      ['trade-certificates', '/(trade)/certificates'],
      ['trade-certificate-new', '/(trade)/certificate/new'],
      ['trade-settings', '/(trade)/settings'],
      ['trade-analytics', '/(trade)/analytics'],
      ['trade-branding', '/(trade)/branding'],
      ['trade-follow-ups', '/(trade)/follow-ups'],
      ['trade-manual-lead', '/(trade)/manual-lead'],
    ];
    for (const [name, route] of tradeRoutes) {
      await gotoAndSettle(page, `${MOBILE_BASE}${route}`, { settleMs: 3500 });
      if (name === 'trade-calendar-week') {
        // Default is the Day view; switch to Week for the capture.
        const weekTab = page.getByText('Week', { exact: true });
        if (await weekTab.count()) {
          await weekTab.first().click();
          await page.waitForTimeout(1500);
        }
      }
      if (name === 'trade-certificate-new') {
        // Open the circuit entry form (the screen starts on an empty state).
        const addCircuit = page.getByText('Add circuit');
        if (await addCircuit.count()) {
          await addCircuit.first().click();
          await page.waitForTimeout(1500);
        }
      }
      report.mobile.push(await snap(page, OUT_MOBILE, name));
    }
    await context.close();
  }

  // --- customer session (Margaret Holloway) ---
  {
    const context = await newMobileContext();
    const page = await context.newPage();
    attachConsoleCollector(page, (consoleErrors.customer = []));
    await loadBusinessViaCode(page); // sets businessStore slug, required by customer login
    // SPA-navigate (no full reload) so the in-memory business survives.
    await page.getByText('Customer login').first().click();
    await page.waitForTimeout(3000);
    await mobileLogin(page, { role: 'customer', email: CREDS.customerEmail });
    const customerRoutes = [
      ['customer-requests', '/(customer)/requests'],
      ['customer-request-chat', `/(customer)/messages?quoteRequestId=${IDS.leadConverted}`],
      ['customer-calendar', '/(customer)/calendar'],
      ['customer-profile', '/(customer)/profile'],
    ];
    for (const [name, route] of customerRoutes) {
      await gotoAndSettle(page, `${MOBILE_BASE}${route}`, { settleMs: 3500 });
      report.mobile.push(await snap(page, OUT_MOBILE, name));
    }
    await context.close();
  }

  fs.writeFileSync(
    path.join(ROOT, 'docs/screenshots/mobile-console-errors.json'),
    JSON.stringify(consoleErrors, null, 2),
  );
  await browser.close();
}

// ------------------------------------------------------------------- main
const target = process.argv[2] || 'both';
fs.mkdirSync(OUT_WEB, { recursive: true });
fs.mkdirSync(OUT_MOBILE, { recursive: true });

const browser = await chromium.launch();
try {
  if (target === 'web' || target === 'both') await captureWeb(browser);
  if (target === 'mobile' || target === 'both') await captureMobile();
} finally {
  await browser.close();
}

fs.writeFileSync(
  path.join(ROOT, 'docs/screenshots/capture-report.json'),
  JSON.stringify(report, null, 2),
);
const okWeb = report.web.filter((r) => r.ok).length;
const okMobile = report.mobile.filter((r) => r.ok).length;
console.log(`web: ${okWeb}/${report.web.length} ok, mobile: ${okMobile}/${report.mobile.length} ok`);
if (report.failures.length) {
  console.log('failures:');
  for (const f of report.failures) console.log(`  - ${f.name}: ${f.error}`);
}
