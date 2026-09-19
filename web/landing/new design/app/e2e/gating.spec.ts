// G25 — Guest chat gating + entitlement/subscription gating from the portal's
// perspective:
//
//  * A passwordless (auto-provisioned) customer is NOT in-app chat-reachable:
//    staff lead reads expose `customer_reachable === false` (5ac841a) and the
//    portal surfaces phone/email contact channels. The portal's own discuss
//    thread is the customer's own async channel and stays available — the
//    gating applies to the tradesperson's composer, which is the app-side
//    ContactCustomerCard (mobile suite covers that half).
//  * The subscription paywall gates STAFF API surfaces (402) but never the
//    customer portal: public config, intake, and customer auth stay live for
//    lapsed tenants (middleware.py exempts /businesses + /customer).
//
// See docs/e2e-coverage-gaps.md rows G25/G8.

import { expect, type Page } from "@playwright/test";
import {
  createTenant,
  customerApi,
  exchangeMagicToken,
  extractToken,
  forgePaddleSubscription,
  seedSentQuote,
  staffApi,
  staffApiRaw,
  stagingConfigured,
  submitIntake,
  uniqueEmail,
  PADDLE_WEBHOOK_SECRET,
  type CustomerSession,
  type Tenant,
  portalTest as test,
} from "./helpers";
import { mailpitConfigured, waitForEmail } from "./mailpit";

let tenant: Tenant;
let customerEmail: string;
let session: CustomerSession;

async function gotoPortal(page: Page, path = "/"): Promise<void> {
  const joiner = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${joiner}slug=${encodeURIComponent(tenant.slug)}`, {
    waitUntil: "domcontentloaded",
  });
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-gating");
  customerEmail = uniqueEmail("gating");

  const intake = await submitIntake(tenant, {
    name: "Gating Customer",
    email: customerEmail,
    description: "Gating journey quote request",
  });
  await seedSentQuote(tenant, {
    title: "Gating quote",
    customerEmail,
    quoteRequestId: intake.id,
  });
  const mail = await waitForEmail(customerEmail, { subjectIncludes: "quote from" });
  session = await exchangeMagicToken(extractToken(mail, "auth/magic"));
});

test("passwordless customer: staff see unreachable on the lead", async () => {
  // Server-side gating signal (5ac841a): auto-provisioned passwordless
  // customers are not chat-reachable — staff must call/email instead.
  const leads = await staffApi<Array<Record<string, any>>>(tenant, "/quote-requests");
  const lead = leads.find((l) => l.customer?.email === customerEmail);
  expect(lead, "lead with customer").toBeTruthy();
  expect(lead!.customer_reachable).toBe(false);
  expect(lead!.customer.has_account).toBe(true); // account exists, just passwordless
});

test("portal quote detail surfaces phone/email contact channels", async ({ page }) => {
  // Seed tenant contact details the way Settings does (PATCH /tenants/me
  // flattens phone/email into the settings JSONB, #143).
  const phone = "07700 900123";
  const email = "office@e2e-portal.trade";
  const patched = await staffApiRaw(tenant, "/tenants/me", {
    method: "PATCH",
    body: { phone, email },
  });
  expect(patched.status).toBe(200);

  // The portal reads them back through the public config that drives the chips.
  const configRes = await fetch(
    `${process.env.TEST_API_BASE_URL}/businesses/${tenant.slug}/public-config`,
  );
  expect(configRes.status).toBe(200);
  const config = (await configRes.json()) as Record<string, unknown>;
  expect(config.contactPhone ?? config.contact_phone).toBe(phone);
  expect(config.replyEmail ?? config.reply_email).toBe(email);

  const quotes = await customerApi<Array<{ id: string }>>(session, "/customer/quotes");
  expect(quotes.length).toBeGreaterThan(0);

  // Sign the portal in by seeding the stored session, as /auth/magic does.
  await page.addInitScript(
    ([slug, token, customer]: [string, string, unknown]) => {
      window.localStorage.setItem(
        `mtp_portal_${slug}`,
        JSON.stringify({
          accessToken: token,
          expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
          customer,
        }),
      );
    },
    [tenant.slug, session.token, session.customer],
  );
  await gotoPortal(page, `/quotes/${quotes[0].id}`);

  // The header Call link and the quote-detail Call/Email-us chips render with
  // working tel:/mailto: targets.
  const headerCall = page.getByRole("link", { name: "Call", exact: true });
  await expect(headerCall).toBeVisible();
  await expect(headerCall).toHaveAttribute("href", `tel:${phone}`);

  const callChip = page.getByRole("link", { name: `Call ${tenant.name}` });
  await expect(callChip).toBeVisible();
  await expect(callChip).toHaveAttribute("href", `tel:${phone}`);

  const emailChip = page.getByRole("link", { name: "Email us" });
  await expect(emailChip).toBeVisible();
  await expect(emailChip).toHaveAttribute("href", new RegExp(`^mailto:${email}`));
});

test("paywall gates staff surfaces but the customer portal stays live", async () => {
  test.skip(!PADDLE_WEBHOOK_SECRET, "TEST_PADDLE_WEBHOOK_SECRET not set");

  // Baseline: no subscription row → beta semantics allow staff access.
  const before = await staffApiRaw(tenant, "/quotes");
  expect(before.status).toBe(200);

  // Lapse the subscription (forged signed Paddle webhook, same as the
  // deployed write suite's G8 drive).
  const canceled = await forgePaddleSubscription(tenant, "subscription.canceled", "canceled");
  expect(canceled.status).toBe(200);

  const gated = await staffApiRaw(tenant, "/quotes");
  expect(gated.status).toBe(402);

  // Customer-facing surfaces stay live (middleware exempts /businesses +
  // /customer — the portal keeps working for a lapsed tenant's customers).
  const config = await fetch(
    `${process.env.TEST_API_BASE_URL}/businesses/${tenant.slug}/public-config`,
  );
  expect(config.status).toBe(200);

  const intake = await submitIntake(tenant, {
    name: "Lapsed Tenant Customer",
    email: uniqueEmail("lapsed"),
    description: "Intake while the tenant subscription is lapsed",
  });
  expect(intake.id).toBeTruthy();

  const quotes = await customerApi<Array<unknown>>(session, "/customer/quotes");
  expect(Array.isArray(quotes)).toBe(true);

  // Reactivate — staff access restored.
  const activated = await forgePaddleSubscription(tenant, "subscription.activated", "active");
  expect(activated.status).toBe(200);
  const after = await staffApiRaw(tenant, "/quotes");
  expect(after.status).toBe(200);
});
