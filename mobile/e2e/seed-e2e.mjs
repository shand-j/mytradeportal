/**
 * Prerequisite-seeding library for the mobile connected-mode regression suite.
 *
 * All helpers take a `tenant` object with `{ token, tenantId, base }` and talk to
 * the backend over HTTP using snake_case wire format. No code runs on import.
 */

const DEFAULT_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8002";

/**
 * Low-level authenticated request helper.
 *
 * @param {object} tenant
 * @param {string} tenant.token
 * @param {string} tenant.tenantId
 * @param {string} [tenant.base]
 * @param {string} path
 * @param {object} [opts]
 * @param {string} [opts.method]
 * @param {object} [opts.body]
 * @param {boolean} [opts.auth]
 */
export async function api(
  tenant,
  path,
  { method = "GET", body, auth = true } = {}
) {
  const base = tenant.base ?? DEFAULT_BASE;
  const headers = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (auth) {
    headers["Authorization"] = `Bearer ${tenant.token}`;
    headers["X-Tenant-ID"] = tenant.tenantId;
  }
  const res = await fetch(`${base}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const payload = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new Error(`${method} ${path} -> ${res.status}: ${text}`);
  }
  return payload;
}

/**
 * Create a trade-side contact for the tenant.
 */
export async function seedContact(
  tenant,
  { name, email, phone, postcode, address }
) {
  return api(tenant, "/contacts", {
    method: "POST",
    body: {
      name,
      email: email ?? null,
      phone: phone ?? null,
      postcode: postcode ?? null,
      address: address ?? null,
    },
  });
}

/**
 * Register a customer account against the tenant's public registration endpoint.
 * Requires `tenant.slug` to route the request.
 */
export async function seedCustomer(
  tenant,
  { email, password, fullName, phone, address = undefined, quoteRequestId = undefined }
) {
  if (!tenant.slug) {
    throw new Error("seedCustomer requires tenant.slug");
  }
  return api(tenant, "/customer/register", {
    method: "POST",
    auth: false,
    body: {
      slug: tenant.slug,
      email,
      password,
      full_name: fullName,
      phone: phone ?? null,
      address: address ?? null,
      quoteRequestId: quoteRequestId ?? null,
    },
  });
}

/**
 * Configure the business services offered by the tenant.
 */
export async function seedBusinessServices(
  tenant,
  services = ["consumer_unit", "ev_charger", "eicr", "other"]
) {
  return api(tenant, "/onboarding/step/services", {
    method: "PATCH",
    body: { step: "services", value: { services } },
  });
}

/**
 * Submit a public quote request so it lands as a lead in the trade app.
 * Requires `tenant.slug`.
 */
export async function seedLead(
  tenant,
  { title, category, contact, urgency = "this_week", structuredData = {} }
) {
  if (!tenant.slug) {
    throw new Error("seedLead requires tenant.slug");
  }
  return api(tenant, `/businesses/${tenant.slug}/quote-requests`, {
    method: "POST",
    auth: false,
    body: {
      contact: {
        name: contact.name,
        email: contact.email ?? null,
        phone: contact.phone ?? null,
        postcode: contact.postcode ?? null,
      },
      category,
      title,
      raw_text: structuredData.notes ?? null,
      structured_data: structuredData,
      urgency,
      preferred_dates: [],
      safety_review_required: false,
      marketing_consent: false,
    },
  });
}

/**
 * Create a scheduled job directly.
 * `contactId` may be omitted, in which case a throwaway contact is created first.
 */
export async function seedScheduledJob(
  tenant,
  { title, scheduledStart, contactId = undefined }
) {
  let resolvedContactId = contactId;
  if (!resolvedContactId) {
    const contact = await seedContact(tenant, {
      name: "E2E Job Contact",
      email: `e2e-job-${Date.now()}@example.com`,
      phone: "07700 900000",
      postcode: "M20 1AA",
      address: "1 E2E Road, Manchester",
    });
    resolvedContactId = contact.id;
  }

  return api(tenant, "/jobs", {
    method: "POST",
    body: {
      contact_id: resolvedContactId,
      title,
      scheduled_start: scheduledStart,
    },
  });
}

/**
 * Create a draft quote and immediately mark it as sent.
 * `contactId` may be omitted; a throwaway contact is created when needed.
 *
 * @param {object} opts
 * @param {string} opts.title
 * @param {string} [opts.contactId]
 * @param {string} [opts.customerEmail]
 * @param {Array<{description: string, quantity: number, unit_price: number}>} [opts.lineItems]
 */
export async function seedSentQuote(
  tenant,
  {
    title,
    contactId = undefined,
    customerEmail = undefined,
    quoteRequestId = undefined,
    lineItems = [{ description: "E2E line item", quantity: 1, unit_price: 500 }],
  }
) {
  let resolvedContactId = contactId;
  if (!resolvedContactId && customerEmail) {
    const contacts = await api(tenant, "/contacts");
    const matched = contacts.find((c) => c.email === customerEmail);
    if (matched) {
      resolvedContactId = matched.id;
    }
  }
  if (!resolvedContactId) {
    const contact = await seedContact(tenant, {
      name: "E2E Quote Contact",
      email: customerEmail ?? `e2e-quote-${Date.now()}@example.com`,
      phone: "07700 900111",
      postcode: "SK8 3NJ",
      address: "2 E2E Road, Stockport",
    });
    resolvedContactId = contact.id;
  }

  const quote = await api(tenant, "/quotes", {
    method: "POST",
    body: {
      contact_id: resolvedContactId,
      title,
      line_items: lineItems,
      vat_rate: 0.2,
    },
  });

  await api(tenant, `/quotes/${quote.id}/send`, { method: "POST" });

  // Link the sent quote back to its originating quote request so it shows in the
  // customer's request history and they can accept/book it.
  if (quoteRequestId) {
    await api(tenant, `/quote-requests/${quoteRequestId}`, {
      method: "PATCH",
      body: {
        quote_id: quote.id,
        status: "converted_to_quote",
      },
    });
  }

  return quote;
}

/**
 * Post an AI follow-up message into a communication thread.
 *
 * The regular POST /communications endpoint overrides sender_role based on the
 * authenticated actor, so staff tokens cannot seed an AI message. Use the
 * backend's dedicated AI follow-up endpoint instead, which calls the real
 * LLM and persists the result as sender_role="ai".
 *
 * `turns` seeds multiple AI follow-ups in a row. The backend force-closes the
 * conversation once it reaches its max follow-up turns (or high confidence), at
 * which point extra calls return the existing closure instantly — so seeding
 * `turns: 3` guarantees the NEXT follow-up after a customer reply is the
 * closure message, regardless of LLM confidence.
 */
export async function seedCommunication(
  tenant,
  { quoteRequestId, turns = 1 }
) {
  let last;
  for (let i = 0; i < turns; i++) {
    last = await api(tenant, `/communications/${quoteRequestId}/ai-followup`, {
      method: "POST",
    });
    // Once the conversation is closed, further turns are no-ops.
    if (last?.ai_metadata?.complete) break;
    // The backend dedupe guard returns an unanswered AI question unchanged,
    // so the next turn only generates after a customer reply. Interleave one
    // (skip after the final turn — the test sends the real reply itself).
    if (i < turns - 1) {
      await api(tenant, "/communications", {
        method: "POST",
        body: {
          quote_request_id: quoteRequestId,
          channel: "in_app_chat",
          body: "It has 8 circuits including the main switch.",
        },
      });
    }
  }
  return last;
}
