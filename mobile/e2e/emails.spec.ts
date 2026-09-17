import { test } from "@playwright/test";
import { CapturedEmail, mailpitConfigured, waitForEmail, waitForEmails } from "./mailpit";
import {
  api,
  createTestTenant,
  expect,
  loginCustomer,
  seedCustomer,
  seedLead,
  seedSentQuote,
  Tenant,
} from "./helpers";

const CUSTOMER_PASSWORD = "E2E-Customer-1";

// Full-lifecycle email spine (G16): one throwaway tenant drives
// quote-ready → acceptance → booking-confirmed on BOTH scheduling paths
// (create-job-from-calendar AND convert-quote-to-job — D5 was a real defect)
// → invoice → payment-received (manual mark-paid — D3 regression guard).
// Every message is asserted in the shared Mailpit mailbox; staging/PR apis
// route outbound email there instead of Resend (docs/ci-pr-environments.md).
//
// Sender conventions (verified against staging Mailpit, 2026-09-17): all
// outbound mail shares one sender ADDRESS — RESEND_FROM_EMAIL on staging
// (quotes@mytradeportal.co.uk), smtp_from_email locally (quotes@mytradeportal.
// local). What distinguishes the categories is the From DISPLAY NAME:
//   * branded customer-facing mail (quote/invoice/booking/payment/chat) goes
//     out as "<Tenant Name> <quotes@…>" so replies reach the business;
//   * transactional account/security mail (magic sign-in, account ready,
//     password resets) goes out under the PLATFORM name ("My Trade Portal")
//     and never impersonates the tenant. It uses no-reply@… when
//     RESEND_NO_REPLY_EMAIL is configured, else the documented fallback to
//     the shared quotes@ address (app/email.py::_resend_from). Staging does
//     NOT set RESEND_NO_REPLY_EMAIL today, so the fallback path is the live
//     contract asserted here.

const runId = Date.now();
const CUSTOMER_A = { email: `emails-a-${runId}@e2e.example.com`, fullName: "E2E Lifecycle Customer A" };
const CUSTOMER_B = { email: `emails-b-${runId}@e2e.example.com`, fullName: "E2E Lifecycle Customer B" };
const QUOTE_TITLE = "E2E Lifecycle consumer unit";
const JOB_A_TITLE = "E2E Calendar booking job";
// createTenant names the business `E2E ${prefix} tenant` — the branded From
// display name is exactly that name (staging-verified).
const BUSINESS_NAME = "E2E emails tenant";
// smtp_from_name default (mtp_shared.config) — the platform identity used on
// transactional mail when no dedicated no-reply address is configured.
const PLATFORM_NAME = "My Trade Portal";

function tomorrowAt(hour: number): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:00:00`;
}

/** Branded customer-facing mail: the tenant's business name on the shared
 *  quotes@ sender (staging verified: `"E2E emails tenant" <quotes@…>`). */
function expectBrandedSender(email: CapturedEmail) {
  expect(email.from).toMatch(/^quotes@/);
  expect(email.fromName).toBe(BUSINESS_NAME);
}

/** Transactional account/security mail: the platform display name — never
 *  the tenant's — on no-reply@ when configured, else the documented shared
 *  sender fallback (app/email.py::_resend_from falls back to
 *  RESEND_FROM_EMAIL when RESEND_NO_REPLY_EMAIL is unset, which is staging's
 *  current configuration). */
function expectTransactionalSender(email: CapturedEmail) {
  expect(email.fromName, "transactional mail must not impersonate the tenant").not.toBe(
    BUSINESS_NAME
  );
  if (email.from.startsWith("no-reply@")) return;
  // Fallback path: shared branded address, but still the platform name.
  expect(email.from).toMatch(/^quotes@/);
  expect(email.fromName).toBe(PLATFORM_NAME);
}

test.describe.serial("P — Email lifecycle sequence (Mailpit)", () => {
  let tenant: Tenant;
  let invoiceNumber: string;

  test.beforeAll(async () => {
    test.skip(!mailpitConfigured(), "MAILPIT_URL / MAILPIT_BASIC_AUTH not set");
    tenant = await createTestTenant("emails");

    // --- Customer A (registered, password-holding): quote → accept →
    //     convert-to-job → invoice → mark-paid. ---
    const leadA = await seedLead(tenant, {
      title: QUOTE_TITLE,
      category: "consumer_unit",
      contact: {
        name: CUSTOMER_A.fullName,
        email: CUSTOMER_A.email,
        phone: "07700 900201",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const registration = await seedCustomer(tenant, {
      email: CUSTOMER_A.email,
      password: CUSTOMER_PASSWORD,
      fullName: CUSTOMER_A.fullName,
      phone: "07700 900201",
      quoteRequestId: leadA.id,
    });
    const contactAId = registration.customer.contact_id as string;
    const quote = await seedSentQuote(tenant, {
      title: QUOTE_TITLE,
      contactId: contactAId,
      quoteRequestId: leadA.id,
      lineItems: [{ description: "Consumer unit replacement", quantity: 1, unit_price: 500 }],
    });

    // Customer accepts (fires the acceptance email + staff notification).
    const auth = await loginCustomer(tenant, {
      email: CUSTOMER_A.email,
      password: CUSTOMER_PASSWORD,
    });
    const customerTenant = { ...tenant, token: (auth.accessToken ?? auth.access_token) as string };
    await api(customerTenant, `/customer/quotes/${quote.id}/accept`, { method: "POST" });

    // Path B (D5): converting the accepted quote to a job lands on a real
    // slot and must email the booking confirmation.
    const scheduledStart = tomorrowAt(9);
    const jobB = await api(tenant, `/quotes/${quote.id}/convert-to-job`, {
      method: "POST",
      body: {
        scheduled_start: scheduledStart,
        scheduled_end: tomorrowAt(11),
      },
    });

    // Invoice FROM the job mirrors the quote; send then mark paid (D3 guard:
    // the manual path must emit the same payment-received mail as Stripe).
    const invoice = await api(tenant, "/invoices", {
      method: "POST",
      body: { contact_id: contactAId, job_id: jobB.id },
    });
    invoiceNumber = invoice.invoice_number as string;
    await api(tenant, `/invoices/${invoice.id}/send`, { method: "POST" });
    await api(tenant, `/invoices/${invoice.id}/mark-paid`, { method: "POST" });

    // --- Customer B (passwordless, auto-provisioned by the guest lead):
    //     tradie creates a job straight from the calendar — the other half
    //     of D5. The booking email carries the account-claim magic link. ---
    await seedLead(tenant, {
      title: "E2E Calendar booking lead",
      category: "consumer_unit",
      contact: {
        name: CUSTOMER_B.fullName,
        email: CUSTOMER_B.email,
        phone: "07700 900202",
        postcode: "SK8 3NJ",
      },
      urgency: "this_week",
    });
    const contacts = (await api(tenant, "/contacts")) as Array<{ id: string; email: string | null }>;
    const contactB = contacts.find((c) => c.email === CUSTOMER_B.email);
    if (!contactB) throw new Error("guest lead did not provision the passwordless customer contact");
    await api(tenant, "/jobs", {
      method: "POST",
      body: {
        contact_id: contactB.id,
        title: JOB_A_TITLE,
        scheduled_start: tomorrowAt(13),
        scheduled_end: tomorrowAt(15),
      },
    });

    // --- Transactional probe: magic sign-in link request. ---
    const res = await fetch(`${tenant.base}/customer/auth/magic/request`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Slug": tenant.slug,
      },
      body: JSON.stringify({ email: CUSTOMER_A.email }),
    });
    expect(res.status).toBe(202);
  });

  test("G16: quote-ready email carries the magic-link CTA from the branded sender", async () => {
    const email = await waitForEmail(CUSTOMER_A.email, {
      subjectIncludes: "Your quote from",
      timeoutMs: 30_000,
    });
    expectBrandedSender(email);
    // Registered customers get the portal magic-link CTA as the primary button.
    expect(email.html).toContain("View and accept your quote");
    expect(email.html).toMatch(/https:\/\//);
    expect(email.html + email.text).toContain(QUOTE_TITLE);
  });

  test("G16: quote acceptance email confirms the pending booking", async () => {
    const email = await waitForEmail(CUSTOMER_A.email, {
      subjectIncludes: "Quote accepted",
      timeoutMs: 30_000,
    });
    // The acceptance confirmation is intentionally PLATFORM-branded
    // (no-reply class): no response is expected, so it must not invite a
    // reply or impersonate the tenant (quote_acceptance.py).
    expectTransactionalSender(email);
    expect(email.html + email.text).toContain(QUOTE_TITLE);
  });

  test("G16: convert-quote-to-job emails booking-confirmed (D5 path B)", async () => {
    const emails = await waitForEmails(CUSTOMER_A.email, {
      subjectIncludes: "Booking confirmed",
      timeoutMs: 30_000,
    });
    const email = emails[0];
    expectBrandedSender(email);
    // The converted job inherits the QUOTE title (convert-to-job takes no
    // title) and the booking email names the job by that title.
    expect(email.html + email.text).toContain(QUOTE_TITLE);
    expect(email.text).toMatch(/Date:/);
  });

  test("G16: create-job-from-calendar emails booking-confirmed with the claim magic link (D5 path A)", async () => {
    const email = await waitForEmail(CUSTOMER_B.email, {
      subjectIncludes: "Booking confirmed",
      timeoutMs: 30_000,
    });
    expectBrandedSender(email);
    expect(email.html + email.text).toContain(JOB_A_TITLE);
    // Passwordless customers get the one-shot account-claim magic-link CTA.
    expect(email.html).toContain("Create your account");
    expect(email.html).toMatch(/https:\/\//);
  });

  test("G16: invoice email then manual payment-received email complete the spine", async () => {
    const invoice = await waitForEmail(CUSTOMER_A.email, {
      subjectIncludes: "Invoice",
      timeoutMs: 30_000,
    });
    expectBrandedSender(invoice);
    expect(invoice.subject).toMatch(/^Invoice \S+ from /);
    // 1 × £500 + 20% VAT = £600.
    expect(invoice.html + invoice.text).toContain("600");
    expect(invoice.html).toMatch(/https:\/\//);

    const payment = await waitForEmail(CUSTOMER_A.email, {
      subjectIncludes: "Payment received",
      timeoutMs: 30_000,
    });
    expectBrandedSender(payment);
    expect(payment.subject).toContain(invoiceNumber);
    // Manual mark-paid must use the non-card copy variant (D3): it must not
    // claim a card receipt was emailed (that copy only ships on the Stripe path).
    expect(payment.html + payment.text).not.toContain("card receipt");
  });

  test("G16: transactional sign-in mail comes from the platform no-reply sender", async () => {
    const email = await waitForEmail(CUSTOMER_A.email, {
      subjectIncludes: "sign-in link",
      timeoutMs: 30_000,
    });
    expect(email.html + email.text).toMatch(/https:\/\//);
    expectTransactionalSender(email);
  });
});
