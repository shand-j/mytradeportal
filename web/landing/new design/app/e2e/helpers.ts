// Staging API + seeding helpers for the portal e2e suite.
//
// Everything here talks to the deployed staging API (TEST_API_BASE_URL) over
// HTTP — tenant bootstrap goes through the setup-token-gated POST /tenants,
// the same path the mobile staging suite uses (mobile/e2e/create-tenant.mjs).
// Tenants are throwaway: every spec file creates its own in beforeAll, so
// tests can never pollute another spec's state. Only used against staging /
// PR environments — never against production.
//
// Requires TEST_API_BASE_URL and TEST_SETUP_TOKEN. Specs skip cleanly when
// either is missing so the suite is inert in unrelated CI jobs.

import { test } from "@playwright/test";
import { createHmac } from "node:crypto";

export const API_BASE = (process.env.TEST_API_BASE_URL ?? "").replace(/\/$/, "");
export const SETUP_TOKEN = process.env.TEST_SETUP_TOKEN ?? "";
export const PADDLE_WEBHOOK_SECRET = process.env.TEST_PADDLE_WEBHOOK_SECRET ?? "";

export function stagingConfigured(): boolean {
  return Boolean(API_BASE && SETUP_TOKEN);
}

export interface Tenant {
  slug: string;
  name: string;
  adminEmail: string;
  adminPassword: string;
  token: string;
  tenantId: string;
}

export interface CustomerSession {
  token: string;
  customer: { id: string; full_name: string; email: string };
}

function slugify(prefix: string): string {
  const safe = prefix
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${safe || "portal"}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}

async function rawApi(
  path: string,
  opts: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
): Promise<{ status: number; json: unknown; text: string }> {
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }
  return { status: res.status, json, text };
}

async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; headers?: Record<string, string> } = {},
): Promise<T> {
  const method = opts.method ?? "GET";
  // Staging occasionally throws transient 5xxs under suite load; retry
  // idempotent GETs with backoff. Mutating requests fail fast.
  const attempts = method === "GET" ? 3 : 1;
  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    const { status, json, text } = await rawApi(path, opts);
    if (status < 200 || status >= 300) {
      lastError = new Error(`${method} ${path} -> ${status}: ${text}`);
      if (status >= 500 && attempt < attempts) {
        await new Promise((resolve) => setTimeout(resolve, attempt * 3_000));
        continue;
      }
      throw lastError;
    }
    return json as T;
  }
  throw lastError ?? new Error(`${method} ${path} failed`);
}

/** Authenticated staff request (bearer + X-Tenant-ID, snake_case wire). */
export function staffApi<T = unknown>(
  tenant: Tenant,
  path: string,
  opts: { method?: string; body?: unknown } = {},
): Promise<T> {
  return api<T>(path, {
    ...opts,
    headers: {
      Authorization: `Bearer ${tenant.token}`,
      "X-Tenant-ID": tenant.tenantId,
    },
  });
}

/** Like staffApi but resolves `{status, json}` on non-2xx for negative asserts. */
export async function staffApiRaw(
  tenant: Tenant,
  path: string,
  opts: { method?: string; body?: unknown } = {},
): Promise<{ status: number; json: unknown }> {
  const { status, json } = await rawApi(path, {
    ...opts,
    headers: {
      Authorization: `Bearer ${tenant.token}`,
      "X-Tenant-ID": tenant.tenantId,
    },
  });
  return { status, json };
}

/** Create a fresh tenant + admin through the setup-token bootstrap, then log
 * in for the staff token. Mirrors mobile/e2e/create-tenant.mjs remote path. */
export async function createTenant(prefix: string): Promise<Tenant> {
  const slug = slugify(prefix);
  const adminEmail = `owner-${slug}@e2e-portal.trade`;
  const adminPassword = "E2E-Password-1";
  const name = `E2E portal ${prefix}`;

  await api("/tenants", {
    method: "POST",
    headers: { "X-Setup-Token": SETUP_TOKEN },
    body: {
      slug,
      name,
      admin_email: adminEmail,
      admin_password: adminPassword,
      admin_name: "E2E Portal Owner",
    },
  });

  // The backend may need a moment to index the new user; retry with backoff.
  let auth: { access_token: string; user: { tenant_id: string } } | null = null;
  let lastError: unknown = null;
  for (let attempt = 0; attempt < 15 && !auth; attempt++) {
    try {
      auth = await api("/auth/token", {
        method: "POST",
        body: { email: adminEmail, password: adminPassword, tenant_slug: slug },
      });
    } catch (err) {
      lastError = err;
      const delay =
        err instanceof Error && err.message.includes("429") ? 15000 : 1000;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }
  if (!auth) {
    throw new Error(`Could not authenticate seeded admin: ${String(lastError)}`);
  }

  currentTenantId = auth.user.tenant_id;
  return {
    slug,
    name,
    adminEmail,
    adminPassword,
    token: auth.access_token,
    tenantId: auth.user.tenant_id,
  };
}

/* ------------------------------------------------------------------ */
/* Public intake / customer seeding                                    */
/* ------------------------------------------------------------------ */

export interface IntakeInput {
  name: string;
  email: string;
  phone?: string;
  address?: string;
  postcode?: string;
  category?: string;
  description: string;
  preferredDates?: string[];
  syncCheck?: boolean;
  entryChannel?: string;
  structuredData?: Record<string, unknown>;
}

export interface QuoteRequestAck {
  id: string;
  status: string;
  reference: string;
  ai_check?: {
    status: "questions" | "ok" | "unavailable";
    question?: string;
    thread_token?: string;
    thread_expires_at?: string;
  };
}

/** Submit the public portal quote-request intake (auto-provisions a
 * passwordless customer when an email is given). */
export function submitIntake(tenant: Tenant, input: IntakeInput): Promise<QuoteRequestAck> {
  return api(`/businesses/${encodeURIComponent(tenant.slug)}/quote-requests`, {
    method: "POST",
    body: {
      contact: {
        name: input.name,
        email: input.email,
        phone: input.phone ?? null,
        address: input.address ?? null,
        postcode: input.postcode ?? null,
      },
      category: input.category ?? null,
      title: input.description.slice(0, 80),
      raw_text: input.description,
      media_urls: [],
      preferred_dates: (input.preferredDates ?? []).map((date) => ({ date })),
      urgency: "this_week",
      safety_review_required: false,
      marketing_consent: false,
      sync_check: input.syncCheck ?? false,
      entry_channel: input.entryChannel ?? "direct",
      structured_data: input.structuredData ?? {},
    },
  });
}

/** Register a full customer account against the tenant's public endpoint
 * (claims a passwordless auto-provisioned account when one exists). */
export async function registerCustomer(
  tenant: Tenant,
  input: { email: string; password: string; fullName: string; quoteRequestId?: string },
): Promise<CustomerSession> {
  const res = (await api("/customer/register", {
    method: "POST",
    body: {
      slug: tenant.slug,
      email: input.email,
      password: input.password,
      full_name: input.fullName,
      quoteRequestId: input.quoteRequestId ?? null,
    },
  })) as {
    access_token?: string;
    accessToken?: string;
    customer: CustomerSession["customer"];
  };
  return { token: res.access_token ?? res.accessToken ?? "", customer: res.customer };
}

export function loginCustomer(
  tenant: Tenant,
  input: { email: string; password: string },
): Promise<{ status: number; json: unknown }> {
  return rawApi("/customer/login", {
    method: "POST",
    body: { slug: tenant.slug, email: input.email, password: input.password },
  }).then(({ status, json }) => ({ status, json }));
}

/** Authenticated customer request (bearer customer JWT; tenant context is
 * taken from the token claims server-side). */
export function customerApi<T = unknown>(
  session: CustomerSession,
  path: string,
  opts: { method?: string; body?: unknown } = {},
): Promise<T> {
  return api<T>(path, {
    ...opts,
    headers: { Authorization: `Bearer ${session.token}` },
  });
}

/** Exchange a raw portal magic-link token (from a Mailpit email) for a
 * customer session, exactly like the portal's /auth/magic page does. */
export async function exchangeMagicToken(token: string): Promise<CustomerSession> {
  const res = (await api("/customer/auth/magic", {
    method: "POST",
    body: { token },
  })) as {
    access_token?: string;
    accessToken?: string;
    customer: CustomerSession["customer"];
  };
  return { token: res.access_token ?? res.accessToken ?? "", customer: res.customer };
}

/** Request a portal magic link (202-generic, tenant-pinned via header). */
export function requestMagicLink(tenant: Tenant, email: string): Promise<{ status: number }> {
  return rawApi("/customer/auth/magic/request", {
    method: "POST",
    headers: { "X-Tenant-Slug": tenant.slug },
    body: { email },
  }).then(({ status }) => ({ status }));
}

/* ------------------------------------------------------------------ */
/* Staff-side document seeding                                         */
/* ------------------------------------------------------------------ */

export async function seedContact(
  tenant: Tenant,
  input: { name: string; email: string; phone?: string; postcode?: string; address?: string },
): Promise<{ id: string }> {
  return staffApi(tenant, "/contacts", {
    method: "POST",
    body: {
      name: input.name,
      email: input.email,
      phone: input.phone ?? null,
      postcode: input.postcode ?? null,
      address: input.address ?? null,
    },
  });
}

/** Create a quote and immediately send it — the customer gets the
 * quote-ready email (document link + magic portal link). Optionally links
 * the quote back to its quote request so it shows in the portal. */
export async function seedSentQuote(
  tenant: Tenant,
  input: {
    title: string;
    contactId?: string;
    customerEmail?: string;
    quoteRequestId?: string;
    lineItems?: Array<{ description: string; quantity: number; unit_price: number }>;
  },
): Promise<{ id: string; title: string }> {
  let contactId = input.contactId;
  if (!contactId) {
    const contacts = await staffApi<Array<{ id: string; email: string | null }>>(tenant, "/contacts");
    contactId = contacts.find((c) => c.email === input.customerEmail)?.id;
  }
  if (!contactId) {
    const contact = await seedContact(tenant, {
      name: "E2E Portal Customer",
      email: input.customerEmail ?? `e2e-quote-${Date.now()}@e2e-portal.trade`,
      phone: "07700 900111",
      postcode: "SK8 3NJ",
      address: "2 E2E Road, Stockport",
    });
    contactId = contact.id;
  }

  const quote = await staffApi<{ id: string }>(tenant, "/quotes", {
    method: "POST",
    body: {
      contact_id: contactId,
      title: input.title,
      line_items:
        input.lineItems ?? [{ description: "E2E line item", quantity: 1, unit_price: 500 }],
      vat_rate: 0.2,
    },
  });
  await staffApi(tenant, `/quotes/${quote.id}/send`, { method: "POST" });
  if (input.quoteRequestId) {
    await staffApi(tenant, `/quote-requests/${input.quoteRequestId}`, {
      method: "PATCH",
      body: { quote_id: quote.id, status: "converted_to_quote" },
    });
  }
  return { id: quote.id, title: input.title };
}

/** Create + send an invoice for a contact. */
export async function seedSentInvoice(
  tenant: Tenant,
  input: {
    contactId: string;
    lineItems?: Array<{ description: string; quantity: number; unit_price: number }>;
  },
): Promise<{ id: string; invoice_number: string }> {
  const invoice = await staffApi<{ id: string; invoice_number: string }>(tenant, "/invoices", {
    method: "POST",
    body: {
      contact_id: input.contactId,
      line_items:
        input.lineItems ?? [{ description: "E2E invoice line", quantity: 1, unit_price: 1200 }],
      vat_rate: 0.2,
    },
  });
  await staffApi(tenant, `/invoices/${invoice.id}/send`, { method: "POST" });
  return invoice;
}

/** Convert an approved quote into a scheduled job (fires the
 * booking-confirmed email to the customer). */
export function convertQuoteToJob(
  tenant: Tenant,
  quoteId: string,
  scheduledStart: string,
  scheduledEnd: string,
): Promise<{ id: string }> {
  return staffApi(tenant, `/quotes/${quoteId}/convert-to-job`, {
    method: "POST",
    body: { scheduled_start: scheduledStart, scheduled_end: scheduledEnd },
  });
}

/* ------------------------------------------------------------------ */
/* Paddle webhook forgery (subscription state drive)                   */
/* ------------------------------------------------------------------ */

/** Forge a signed Paddle subscription webhook event and deliver it to the
 * staging API — mirrors tests_deployed/webhook_signing.py. */
export async function forgePaddleSubscription(
  tenant: Tenant,
  eventType: "subscription.activated" | "subscription.canceled" | "subscription.updated",
  subscriptionStatus: string,
): Promise<{ status: number }> {
  if (!PADDLE_WEBHOOK_SECRET) {
    throw new Error("TEST_PADDLE_WEBHOOK_SECRET not set");
  }
  const ts = Math.floor(Date.now() / 1000).toString();
  const body = JSON.stringify({
    event_id: `evt_portal_${Math.random().toString(36).slice(2, 14)}`,
    event_type: eventType,
    data: {
      id: `sub_portal_${Math.random().toString(36).slice(2, 14)}`,
      status: subscriptionStatus,
      custom_data: { tenant_id: tenant.tenantId },
      items: [{}],
    },
  });
  const h1 = createHmac("sha256", PADDLE_WEBHOOK_SECRET)
    .update(`${ts}:${body}`)
    .digest("hex");
  const { status } = await rawApi("/webhooks/paddle", {
    method: "POST",
    headers: {
      "Paddle-Signature": `ts=${ts};h1=${h1}`,
    },
    body: JSON.parse(body),
  });
  return { status };
}

/* ------------------------------------------------------------------ */
/* Link extraction + misc                                              */
/* ------------------------------------------------------------------ */

/** Pull a raw token out of an emailed portal link
 * (`https://{slug}.mytradeportal.co.uk/{path}?token=…`). */
export function extractToken(email: { text: string; html: string }, path: string): string {
  const re = new RegExp(
    `https://[^\\s"']+/${path.replace(/\//g, "\\/")}\\?[^\\s"']*token=([^&\\s"']+)`,
  );
  const fromText = email.text.match(re);
  if (fromText) return fromText[1];
  const fromHtml = email.html.match(re);
  if (fromHtml) return fromHtml[1];
  throw new Error(`No /${path} link with token found in email`);
}

/** Extract the path of a public document link (`/quote/{token}` etc). */
export function extractDocumentPath(
  email: { text: string; html: string },
  kind: "quote" | "invoice" | "pay",
): string {
  const re = new RegExp(`https://[^\\s"']+/${kind}/([a-zA-Z0-9_\\-]+)`);
  const fromText = email.text.match(re);
  if (fromText) return `/${kind}/${fromText[1]}`;
  const fromHtml = email.html.match(re);
  if (fromHtml) return `/${kind}/${fromHtml[1]}`;
  throw new Error(`No /${kind}/ token link found in email`);
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 100000)}@e2e-portal.trade`;
}

/* ------------------------------------------------------------------ */
/* Browser CORS + tenant-header workaround (staging env bugs — see PR) */
/* ------------------------------------------------------------------ */

/**
 * Staging deployment bug (env, not product code): the staging API's CORS
 * allowlist (`ALLOWED_ORIGINS` / origin regex in services/api/app/main.py)
 * permits `*.mytradeportal.co.uk` and `web-mytradeportal-pr-*.up.railway.app`
 * but NOT the staging landing origin (`landing-staging-*.up.railway.app`), so
 * the staging portal bundle cannot call the staging API from a browser at
 * all. Until the allowlist is fixed, tests replay API responses with the
 * `Access-Control-Allow-Origin` header added — every other byte of the
 * request/response goes to the real services untouched.
 *
 * Second shim: tenant-scoped routes that resolve the tenant from the Host
 * subdomain (e.g. GET/POST /communications, used by the portal discuss
 * thread) 401 when the page runs on the non-subdomain staging origin —
 * there is no `{slug}.mytradeportal.co.uk` host to infer from. On a real
 * tenant subdomain this works without the header. We inject `X-Tenant-ID`
 * (the tenant the current spec created) so those requests resolve exactly as
 * they would on the tenant subdomain. The API still cross-checks the header
 * against the bearer token's tenant claim, so this weakens nothing.
 */
let currentTenantId: string | null = null;

export const portalTest = test.extend<{ page: import("@playwright/test").Page }>({
  page: async ({ page }, use) => {
    if (API_BASE) {
      await page.route(`${API_BASE}/**`, async (route) => {
        const requestHeaders = route.request().headers();
        const forwarded: Record<string, string> = {};
        for (const [key, value] of Object.entries(requestHeaders)) {
          if (!key.startsWith(":")) forwarded[key] = value;
        }
        if (currentTenantId && !forwarded["x-tenant-id"]) {
          forwarded["x-tenant-id"] = currentTenantId;
        }
        const response = await route.fetch({ headers: forwarded });
        const headers = { ...response.headers() };
        const origin = requestHeaders["origin"];
        if (origin) headers["access-control-allow-origin"] = origin;
        headers["access-control-allow-credentials"] = "true";
        await route.fulfill({ response, headers });
      });
    }
    await use(page);
    await page.unrouteAll({ behavior: "ignoreErrors" }).catch(() => {});
  },
});
