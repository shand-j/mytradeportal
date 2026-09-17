// G22 — Booking flow: customer accepts with preferred dates, tradie schedules
// (quote → job convert) and the customer gets the booking-confirmed email
// with magic link + claim CTA (passwordless accounts only); the customer's
// own booking request via POST /customer/appointments shows in their list.
//
// See docs/e2e-coverage-gaps.md row G22.

import { expect } from "@playwright/test";
import { mailpitConfigured, waitForEmail } from "./mailpit";
import {
  convertQuoteToJob,
  createTenant,
  customerApi,
  exchangeMagicToken,
  extractToken,
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
let customerEmail: string;
let session: CustomerSession;

test.beforeAll(async () => {
  test.skip(!stagingConfigured(), "TEST_API_BASE_URL / TEST_SETUP_TOKEN not set");
  test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
  tenant = await createTenant("portal-booking");
  customerEmail = uniqueEmail("booking");

  const intake = await submitIntake(tenant, {
    name: "Portal Booking Customer",
    email: customerEmail,
    description: "Portal booking journey",
  });
  const quote = await seedSentQuote(tenant, {
    title: "Booking flow quote",
    customerEmail,
    quoteRequestId: intake.id,
  });

  // Customer accepts with preferred dates via the API their portal uses.
  const readyMail = await waitForEmail(customerEmail, { subjectIncludes: "quote from" });
  session = await exchangeMagicToken(extractToken(readyMail, "auth/magic"));
  const date = new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10);
  await customerApi(session, `/customer/quotes/${quote.id}/accept`, {
    method: "POST",
    body: { preferred_dates: [{ date }] },
  });
});

test("scheduling the accepted quote emails booking confirmation with claim CTA", async () => {
  const quotes = await staffApi<Array<Record<string, any>>>(tenant, "/quotes");
  const quote = quotes.find((q) => q.title === "Booking flow quote")!;

  const start = new Date(Date.now() + 6 * 86_400_000);
  start.setUTCHours(9, 0, 0, 0);
  const end = new Date(start.getTime() + 2 * 3_600_000);
  await convertQuoteToJob(tenant, quote.id as string, start.toISOString(), end.toISOString());

  const mail = await waitForEmail(customerEmail, { subjectIncludes: "Booking confirmed" });
  // Tenant-branded, Reply-To the tradesperson; visit details in the body
  // (server-side formatting is UTC, so schedule on a UTC boundary).
  expect(mail.text).toContain("09:00");
  expect(mail.text).toMatch(/Date:|Visit|date/i);

  // Claim CTA present because the account is still passwordless — a magic
  // link whose next=/claim on the tenant portal subdomain.
  expect(mail.html + mail.text).toMatch(/auth\/magic\?[^\s]*next=\/claim/);
  expect(extractToken(mail, "auth/magic")).toBeTruthy();
});

test("customer booking request via POST /customer/appointments appears in their list", async () => {
  const start = new Date(Date.now() + 8 * 86_400_000);
  start.setHours(10, 0, 0, 0);
  const end = new Date(start.getTime() + 60 * 60 * 1000);

  const created = await customerApi<{ id: string; title: string }>(session, "/customer/appointments", {
    method: "POST",
    body: {
      title: "Site visit — portal booking request",
      start_at: start.toISOString(),
      end_at: end.toISOString(),
    },
  });
  expect(created.id).toBeTruthy();

  const list = await customerApi<Array<{ id: string; title: string }>>(
    session,
    "/customer/appointments",
  );
  expect(list.map((a) => a.id)).toContain(created.id);
});

test("a claimed (password) customer gets no claim CTA in the booking email", async () => {
  // Once the account has a password the booking confirmation must not carry
  // the "Create your account" block (portal_links: claim_url only for
  // passwordless customers).
  const email = uniqueEmail("booking-claimed");
  const intake = await submitIntake(tenant, {
    name: "Claimed Booking Customer",
    email,
    description: "Claimed customer booking journey",
  });
  const quote = await seedSentQuote(tenant, {
    title: "Claimed customer quote",
    customerEmail: email,
    quoteRequestId: intake.id,
  });

  const readyMail = await waitForEmail(email, { subjectIncludes: "quote from" });
  const claimedSession = await exchangeMagicToken(extractToken(readyMail, "auth/magic"));
  await customerApi(claimedSession, `/customer/quotes/${quote.id}/accept`, {
    method: "POST",
    body: {},
  });

  // Claim the account first (same shape as the portal claim page).
  await requestMagicLink(tenant, email);
  const signIn = await waitForEmail(email, { subjectIncludes: "sign-in link" });
  const claimRes = await fetch(
    `${process.env.TEST_API_BASE_URL}/customer/auth/claim`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: extractToken(signIn, "auth/magic"), password: "Booked-1-x" }),
    },
  );
  expect(claimRes.status).toBe(200);

  const start = new Date(Date.now() + 7 * 86_400_000);
  start.setHours(13, 0, 0, 0);
  const end = new Date(start.getTime() + 2 * 3_600_000);
  await convertQuoteToJob(tenant, quote.id, start.toISOString(), end.toISOString());

  const mail = await waitForEmail(email, { subjectIncludes: "Booking confirmed" });
  expect(mail.html + mail.text).not.toMatch(/auth\/magic/i);
});
