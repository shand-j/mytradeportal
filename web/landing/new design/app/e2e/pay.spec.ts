// G23 — Portal invoices & pay: invoice list/detail render status + totals,
// the pay shell is graceful when the tenant has no Stripe connection, and the
// view-only /invoice/:token page works with no account at all.
//
// The positive card-payment path (Stripe-connected tenant → Payment Element →
// webhook → paid) is G1/G2 — Wave 1 of the coverage plan (needs a
// Stripe-connected seed); it is deliberately left as a fixme below rather
// than half-covered here.
//
// See docs/e2e-coverage-gaps.md row G23.

import { expect, type Page } from "@playwright/test";
import { mailpitConfigured, waitForEmail } from "./mailpit";
import {
  createTenant,
  customerApi,
  exchangeMagicToken,
  extractDocumentPath,
  extractToken,
  seedSentInvoice,
  seedSentQuote,
  staffApi,
  stagingConfigured,
  submitIntake,
  uniqueEmail,
  type CustomerSession,
  type Tenant,
  portalTest as test,
} from "./helpers";

let tenant: Tenant;
let customerEmail: string;

async function gotoPortal(page: Page, path = "/"): Promise<void> {
  const joiner = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${joiner}slug=${encodeURIComponent(tenant.slug)}`, {
    waitUntil: "domcontentloaded",
  });
}

/** Sign the shared customer in via the newest magic-link email. */
async function signIn(page: Page): Promise<CustomerSession> {
  await gotoPortal(page, "/invoices");
  // Invoice email subject is "Invoice INV-… from {business}" (capital I) —
  // Mailpit's subject filter is case-sensitive.
  const mail = await waitForEmail(customerEmail, { subjectIncludes: "Invoice " });
  const token = extractToken(mail, "auth/magic");
  const session = await exchangeMagicToken(token);
  await gotoPortal(
    page,
    `/auth/magic?token=${encodeURIComponent(token)}&next=${encodeURIComponent("/invoices")}`,
  );
  await expect(page.getByRole("heading", { name: "Invoices" })).toBeVisible();
  return session;
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-pay");
  customerEmail = uniqueEmail("pay");

  const intake = await submitIntake(tenant, {
    name: "Portal Pay Customer",
    email: customerEmail,
    description: "Portal pay journey",
  });
  // A quote + invoice so the customer has documents on the portal.
  await seedSentQuote(tenant, {
    title: "Pay journey quote",
    customerEmail,
    quoteRequestId: intake.id,
  });
  const contacts = await staffApi<Array<Record<string, any>>>(tenant, "/contacts");
  const contactId = contacts.find((c) => c.email === customerEmail)!.id as string;
  await seedSentInvoice(tenant, { contactId });
});

test("invoice list and detail render without a card option for a non-connected tenant", async ({
  page,
}) => {
  const session = await signIn(page);

  await expect(page.getByText(/Invoice INV-/)).toBeVisible();
  await expect(page.getByText("Awaiting response").first()).toBeVisible();

  await page.getByText(/Invoice INV-/).first().click();
  await expect(page.getByText("Subtotal (ex VAT)")).toBeVisible();
  await expect(page.getByText(/VAT \(20%\)/)).toBeVisible();
  await expect(page.getByText("Total").last()).toBeVisible();

  // Graceful pay shell: no Stripe connection → no card form, no pay button —
  // the fallback copy points at the invoice email link / phone.
  await expect(
    page.getByText(/To pay online, use the secure pay link in your invoice email/),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Pay securely/ })).toHaveCount(0);
  await expect(page.locator(".StripeElement, [data-testid='card-element']")).toHaveCount(0);

  // Server-side: the invoice carries no payment handoff for this tenant.
  const invoices = await customerApi<Array<Record<string, any>>>(session, "/customer/invoices");
  const invoice = invoices[0];
  expect(invoice.payment_url ?? null).toBeNull();
  expect(invoice.payment_client_secret ?? null).toBeNull();
});

test("view-only /invoice/:token page opens with no account", async ({ page }) => {
  const mail = await waitForEmail(customerEmail, { subjectIncludes: "Invoice" });
  const docPath = extractDocumentPath(mail, "invoice");

  // Public token page on the marketing origin — no slug, no session.
  await page.goto(docPath, { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/Invoice INV-/)).toBeVisible();
  await expect(page.getByText("Total").last()).toBeVisible();
  await expect(page.getByText(/Outstanding|Awaiting response|Sent|Issued/i).first()).toBeVisible();
  // No portal sign-in gate on the public document page.
  await expect(page.getByText("Sign in to continue")).toHaveCount(0);
});

test.fixme("Stripe-connected tenant: card pay shell → sandbox card → paid", async () => {
  // FIXME(Wave 1, G1/G2 — not yet covered): needs a Stripe-connected tenant
  // seed (POST /payments/connect + test-mode onboarding short-circuit) and
  // the staging Stripe webhook endpoint registered in the dashboard (see
  // "Stripe webhooks on staging" in docs/e2e-coverage-gaps.md). Until then
  // the portal pay shell is only covered in its graceful no-connection state
  // above.
});
