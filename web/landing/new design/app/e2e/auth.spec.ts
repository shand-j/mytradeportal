// G20 — Magic-link auth & account claim: passwordless sign-in, single-use
// tokens, object-level isolation, no account enumeration, app-register claim
// (no 409), booking-email claim link sets a password and flips comms
// preference to app.
//
// See docs/e2e-coverage-gaps.md row G20. Runs against staging landing
// (`?slug=` portal override) + staging API + Mailpit.

import { expect, type Page } from "@playwright/test";
import { mailpitConfigured, waitForEmail, waitForEmails, assertNoEmail } from "./mailpit";
import {
  convertQuoteToJob,
  createTenant,
  customerApi,
  exchangeMagicToken,
  extractToken,
  loginCustomer,
  registerCustomer,
  requestMagicLink,
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

/** Open a portal page with the `?slug=` host override. */
async function gotoPortal(page: Page, path = "/"): Promise<void> {
  const joiner = path.includes("?") ? "&" : "?";
  await page.goto(`${path}${joiner}slug=${encodeURIComponent(tenant.slug)}`, {
    waitUntil: "domcontentloaded",
  });
}

/** Drive the SignInPanel: enter an email, wait for the magic email, then
 * follow the link (token re-targeted at the test landing origin). Returns the
 * raw magic token so tests can assert single-use behaviour. */
async function signInViaMagicLink(page: Page, email: string): Promise<string> {
  await gotoPortal(page, "/quotes");
  await expect(page.getByText("Sign in to continue")).toBeVisible({ timeout: 45_000 });
  await page.locator('input[type="email"]').first().fill(email);
  await page.getByRole("button", { name: "Email me a link" }).click();
  await expect(page.getByText("Check your inbox")).toBeVisible();

  const mail = await waitForEmail(email, { subjectIncludes: "sign-in link" });
  const token = extractToken(mail, "auth/magic");
  await gotoPortal(
    page,
    `/auth/magic?token=${encodeURIComponent(token)}&next=${encodeURIComponent("/quotes")}`,
  );
  // Wait for the exchange + redirect to fully settle before touching other
  // pages (staging latency can leave the consume in flight otherwise).
  await expect(page).toHaveURL(/\/quotes/, { timeout: 45_000 });
  await expect(page.getByRole("heading", { name: "Quotes" })).toBeVisible({ timeout: 45_000 });
  return token;
}

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-auth");
});

test("magic link signs the customer in and the session persists", async ({ page }) => {
  const email = uniqueEmail("magic");
  const ack = await submitIntake(tenant, {
    name: "Magic Link Customer",
    email,
    description: "Magic link sign-in journey",
  });

  const token = await signInViaMagicLink(page, email);

  // Consumed: redirected to /quotes with an empty state (no quotes yet).
  await expect(page).toHaveURL(/\/quotes/);
  await expect(page.getByRole("heading", { name: "Quotes" })).toBeVisible();
  await expect(page.getByText("No quotes yet")).toBeVisible();
  await expect(page.getByText("Sign in to continue")).toHaveCount(0);

  // The quote REQUEST the customer made shows up on their portal.
  const session = await exchangeMagicToken(token);
  const requests = await customerApi<Array<{ id: string }>>(session, "/customer/quote-requests");
  expect(requests.map((r) => r.id)).toContain(ack.id);

  // Session persists across a full reload (localStorage mirror).
  await gotoPortal(page, "/quotes");
  await expect(page.getByText("Sign in to continue")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Quotes" })).toBeVisible();
});

test("re-issuing a magic link revokes the earlier one (rotation, not single-use)", async ({
  page,
}) => {
  // Contract (app/portal_links.py): re-issuing revokes earlier still-valid
  // tokens so only the NEWEST emailed link signs in. Exchange itself does not
  // revoke — links stay valid until expiry/rotation (email-scanner safe).
  const email = uniqueEmail("rotation");
  await submitIntake(tenant, {
    name: "Rotation Customer",
    email,
    description: "Magic link rotation journey",
  });

  // Link 1 (never consumed).
  await requestMagicLink(tenant, email);
  const first = await waitForEmail(email, { subjectIncludes: "sign-in link" });
  const firstToken = extractToken(first, "auth/magic");

  // Link 2 issued — rotates the first one out.
  await requestMagicLink(tenant, email);
  const second = (await waitForEmails(email, {
    subjectIncludes: "sign-in link",
    minCount: 2,
  }))[0]; // newest first
  const secondToken = extractToken(second, "auth/magic");

  // The stale link lands on the expired/used state with a resend option…
  await gotoPortal(page, `/auth/magic?token=${encodeURIComponent(firstToken)}`);
  await expect(page.getByText(/This link has expired or has already been used/)).toBeVisible();

  // …and the newest link signs in.
  await gotoPortal(page, 
    `/auth/magic?token=${encodeURIComponent(secondToken)}&next=${encodeURIComponent("/quotes")}`,
  );
  await expect(page.getByRole("heading", { name: "Quotes" })).toBeVisible();
});

test("magic-link request never reveals whether an account exists", async ({ page }) => {
  const unknown = uniqueEmail("no-such-account");
  await gotoPortal(page, "/quotes");
  await page.locator('input[type="email"]').first().fill(unknown);
  await page.getByRole("button", { name: "Email me a link" }).click();

  // Identical UX whether or not the account exists.
  await expect(page.getByText("Check your inbox")).toBeVisible();

  // And no email is ever delivered to an unknown address.
  await assertNoEmail(unknown, { windowMs: 12_000 });
});

test("object isolation: customer A cannot open customer B's quote", async ({ page }) => {
  const emailA = uniqueEmail("iso-a");
  const emailB = uniqueEmail("iso-b");
  await submitIntake(tenant, { name: "Iso A", email: emailA, description: "Isolation A job" });
  const intakeB = await submitIntake(tenant, {
    name: "Iso B",
    email: emailB,
    description: "Isolation B job",
  });

  // B gets a sent quote linked to their request.
  const quoteB = await seedSentQuote(tenant, {
    title: "Iso B private quote",
    customerEmail: emailB,
    quoteRequestId: intakeB.id,
  });

  // A signs in and tries to open B's quote by id.
  await signInViaMagicLink(page, emailA);
  await gotoPortal(page, `/quotes/${quoteB.id}`);
  await expect(page.getByText(/couldn't find that quote/i)).toBeVisible();

  // And B's quote is absent from A's list.
  await gotoPortal(page, "/quotes");
  await expect(page.getByText("Iso B private quote")).toHaveCount(0);
});

test("app register against the passwordless account claims it (no 409)", async () => {
  const email = uniqueEmail("claimreg");
  const intake = await submitIntake(tenant, {
    name: "Register Claim Customer",
    email,
    description: "Register claims the auto-provisioned account",
  });

  const password = "Claimed-pass-1";
  const session: CustomerSession = await registerCustomer(tenant, {
    email,
    password,
    fullName: "Register Claim Customer",
    quoteRequestId: intake.id,
  });
  expect(session.token).toBeTruthy();

  // Login now works with the claimed password.
  const login = await loginCustomer(tenant, { email, password });
  expect(login.status).toBe(200);

  // NOTE: registering does NOT flip the comms preference to app — only the
  // claim flow (portal_links.flip_preferred_contact_to_app) and push-token
  // registration do. The flip is asserted in the claim-link test below.
});

test("booking-email claim link sets a password, is one-shot, flips preference", async ({
  page,
}) => {
  // End-to-end chain: booking-confirmation claim CTA (magic link with
  // next=/claim) → PortalMagicAuth consumes and forwards the token →
  // PortalClaim sets the password via POST /customer/auth/claim, which
  // revokes the token and flips the comms preference to app.
  const email = uniqueEmail("claimlink");
  const intake = await submitIntake(tenant, {
    name: "Claim Link Customer",
    email,
    description: "Claim link from booking confirmation",
  });
  const quote = await seedSentQuote(tenant, {
    title: "Claim link quote",
    customerEmail: email,
    quoteRequestId: intake.id,
  });

  // Customer accepts the quote with preferred dates; tradie schedules it →
  // booking-confirmed email with the claim CTA (passwordless account).
  const readyMail = await waitForEmail(email, { subjectIncludes: "quote from" });
  const magicToken = extractToken(readyMail, "auth/magic");
  const session = await exchangeMagicToken(magicToken);
  const date = new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10);
  await customerApi(session, `/customer/quotes/${quote.id}/accept`, {
    method: "POST",
    body: { preferred_dates: [{ date }] },
  });

  const start = new Date(Date.now() + 6 * 86_400_000);
  start.setHours(9, 0, 0, 0);
  const end = new Date(start.getTime() + 2 * 3_600_000);
  await convertQuoteToJob(tenant, quote.id, start.toISOString(), end.toISOString());

  const booking = await waitForEmail(email, { subjectIncludes: "Booking confirmed" });
  // Claim CTA = magic link whose next=/claim (single token type; the claim
  // page is where the password gets set).
  expect(booking.text + booking.html).toMatch(/auth\/magic\?[^\s]*next=\/claim/);
  const claimToken = extractToken(booking, "auth/magic");

  // Follow the claim link: set a password, land on the welcome screen with a
  // live session.
  await gotoPortal(
    page,
    `/auth/magic?token=${encodeURIComponent(claimToken)}&next=${encodeURIComponent("/claim")}`,
  );
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  const password = "ClaimLink-1-x";
  await page.locator("#claim-password").fill(password);
  await page.locator("#claim-confirm").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Your account is ready" })).toBeVisible();

  // One-shot: replaying the claim token lands on the invalid state.
  await gotoPortal(
    page,
    `/auth/magic?token=${encodeURIComponent(claimToken)}&next=${encodeURIComponent("/claim")}`,
  );
  await expect(page.getByText(/expired or has already been used/)).toBeVisible();

  // Password set → app-style login works; comms preference flipped to app.
  const login = await loginCustomer(tenant, { email, password });
  expect(login.status).toBe(200);
  const contacts = await staffApi<Array<Record<string, any>>>(tenant, "/contacts");
  const contact = contacts.find((c) => c.email?.toLowerCase() === email.toLowerCase());
  expect(contact!.preferred_contact_method).toBe("app");
});
