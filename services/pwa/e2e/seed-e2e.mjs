/**
 * Seed connected-mode E2E data into the demo tenant: one contact, one
 * outstanding quote, and one scheduled job. Idempotent — skips if the E2E
 * quote already exists. Talks to the API over HTTP (snake_case wire format),
 * so it works against any running stack. Node 18+ (global fetch).
 */
const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "owner@demo.trade";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "demo123";
const SLUG = process.env.E2E_TENANT_SLUG ?? "demo";

const QUOTE_TITLE = "E2E Consumer unit upgrade";
const JOB_TITLE = "E2E EV charger install";

async function api(path, { method = "GET", token, tenantId, body } = {}) {
  const headers = { Accept: "application/json" };
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (tenantId) headers["X-Tenant-ID"] = tenantId;
  const res = await fetch(`${API}${path}`, {
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

async function main() {
  const auth = await api("/auth/token", {
    method: "POST",
    body: { email: EMAIL, password: PASSWORD, tenant_slug: SLUG },
  });
  const token = auth.access_token;
  const tenantId = auth.user.tenant_id;
  const ctx = { token, tenantId };

  const quotes = await api("/quotes", ctx);
  const jobs = await api("/jobs", ctx);
  const haveQuote = Array.isArray(quotes) && quotes.some((q) => q.title === QUOTE_TITLE);
  const haveJob = Array.isArray(jobs) && jobs.some((j) => j.title === JOB_TITLE);

  if (haveQuote && haveJob) {
    console.log("E2E data already present; skipping seed.");
    return;
  }

  // Reuse the E2E contact if it exists, otherwise create it.
  const contacts = await api("/contacts", ctx);
  let contact = Array.isArray(contacts)
    ? contacts.find((c) => c.name === "E2E Sarah Beta")
    : undefined;
  if (!contact) {
    contact = await api("/contacts", {
      ...ctx,
      method: "POST",
      body: {
        name: "E2E Sarah Beta",
        email: "e2e.sarah@example.com",
        phone: "07700 900555",
        postcode: "M20 1AA",
        address: "1 E2E Road, Manchester",
      },
    });
  }

  if (!haveQuote) {
    await api("/quotes", {
      ...ctx,
      method: "POST",
      body: {
        contact_id: contact.id,
        title: QUOTE_TITLE,
        line_items: [
          { description: "Consumer unit replacement - 6-8 circuits", quantity: 1, unit_price: 520 },
        ],
        vat_rate: 0.2,
      },
    });
  }

  if (!haveJob) {
    // The backend's scheduled_start column is timezone-naive, so send a naive
    // local datetime (no trailing "Z") to avoid an asyncpg DataError.
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const scheduledStart = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00:00`;
    await api("/jobs", {
      ...ctx,
      method: "POST",
      body: {
        contact_id: contact.id,
        title: JOB_TITLE,
        scheduled_start: scheduledStart,
      },
    });
  }

  console.log("Seeded E2E data for tenant", SLUG, `(quote=${!haveQuote}, job=${!haveJob})`);
}

main().catch((err) => {
  console.error("Seed failed:", err.message);
  process.exit(1);
});
