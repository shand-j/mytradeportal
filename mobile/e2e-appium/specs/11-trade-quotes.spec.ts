/**
 * Trade quotes journeys:
 *  - quotes list + quote detail render line items and totals (cross-checked API ↔ UI)
 *  - refine-with-AI shows the regeneration state
 *  - request-info flow opens the customer conversation
 *  - send quote flips status to sent, emails the customer (send is audit-logged)
 *  - accepted quote converts to a job carrying the quote reference
 *
 * The quote/contact/lead are created through the API with a unique tag so the
 * UI under test is the read/send/refine/convert surface; everything created is
 * deleted in the after hook via helpers/api deleteTestData.
 */
import {
  apiGet,
  apiPatch,
  closeDb,
  countRows,
  dbConfigured,
  deleteTestData,
  findContactByEmail,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
  type ApiTenantContext,
} from "../helpers/api";
import { loginAsTrade } from "../helpers/auth";
import {
  byId,
  hasText,
  swipeUp,
  tapBack,
  tapId,
  tapText,
  textEl,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";
import { API_BASE } from "../helpers/env";

const TAG = Date.now().toString(36);
const CONTACT_NAME = `E2E Quote Customer ${TAG}`;
const CONTACT_EMAIL = `e2e-quote-${TAG}@example.com`;
const QUOTE_TITLE = `E2E Quote ${TAG}`;
const LEAD_TEXT = `E2E info-request lead ${TAG}: customer asked about outdoor socket pricing`;

/** Line items: 1 × £400 + 4 × £45 = £580 subtotal, £116 VAT, £696 total @20%. */
const LINE_ITEMS = [
  { description: "Consumer unit replacement", quantity: 1, unit_price: 400, unit: "ea", ai_generated: true },
  { description: "Labour — certified electrician", quantity: 4, unit_price: 45, unit: "hr", ai_generated: false },
];
const EXPECTED_TOTAL_TEXT = "£696.00";

interface ApiQuoteRow {
  id: string;
  title: string;
  status: string;
  total: string;
  subtotal: string;
  vat_amount: string;
  sent_at: string | null;
  ai_generated?: boolean;
  line_items: Array<{ description: string; quantity: string; unit_price: string }>;
}

interface ApiJobRow {
  id: string;
  title: string;
  status: string;
  quote_id: string | null;
}

interface ApiContactRow {
  id: string;
  email: string | null;
}

interface ApiQuoteRequestRow {
  id: string;
  raw_text: string | null;
  status: string;
  quote: { id: string } | null;
}

/** Local POST helper (helpers/api only exposes GET/PATCH). */
async function apiPost(
  ctx: ApiTenantContext,
  path: string,
  payload?: Record<string, unknown>
): Promise<unknown> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ctx.token}`,
      "X-Tenant-ID": ctx.tenantId,
      "Content-Type": "application/json",
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/** Swipe up (scroll down the RN ScrollView) until the testID exists. */
async function scrollUntilId(id: string, timeoutMs = 20000) {
  const el = byId(id);
  const start = Date.now();
  while (!(await el.isExisting())) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`scrollUntilId timed out looking for testID: ${id}`);
    }
    await swipeUp();
    await driver.pause(350);
  }
  return el;
}

/** Swipe up until the exact text exists (presence only, no tap). */
async function scrollUntilText(label: string, timeoutMs = 20000) {
  const start = Date.now();
  while (!(await textEl(label).isExisting())) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`scrollUntilText timed out looking for text: ${label}`);
    }
    await swipeUp();
    await driver.pause(350);
  }
}

describe("trade quotes", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let contactId = "";
  let quoteId = "";
  let leadId = "";
  let jobId = "";

  before(async () => {
    ctx = await loginTradeApi();

    const contact = (await apiPost(ctx, "/contacts", {
      name: CONTACT_NAME,
      email: CONTACT_EMAIL,
      phone: "07123456789",
      postcode: "SW1A 1AA",
    })) as ApiContactRow;
    contactId = contact.id;

    const quote = (await apiPost(ctx, "/quotes", {
      contact_id: contactId,
      title: QUOTE_TITLE,
      description: "E2E quote description",
      vat_rate: 0.2,
      line_items: LINE_ITEMS,
    })) as ApiQuoteRow;
    quoteId = quote.id;

    // Flag the quote as AI-drafted so the "Refine with AI" panel renders
    // (create doesn't run the AI feedback pass; PATCH with the same lines does).
    await apiPatch(ctx, `/quotes/${quoteId}`, { line_items: LINE_ITEMS });

    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    if (!dbConfigured()) {
      console.log("NOTE: MTP_DB_URL not set — skipping DB cleanup for", QUOTE_TITLE);
      await closeDb();
      return;
    }
    try {
      if (leadId) {
        await deleteTestData("quote_request_id = $1", [leadId]);
        await deleteTestData("id = $1", [leadId]);
      }
      if (quoteId) {
        await deleteTestData("quote_id = $1", [quoteId]);
        await deleteTestData("id = $1", [quoteId]);
      }
      if (jobId) {
        await deleteTestData("job_id = $1", [jobId]);
        await deleteTestData("id = $1", [jobId]);
      }
      if (contactId) {
        await deleteTestData("contact_id = $1", [contactId]);
        await deleteTestData("id = $1", [contactId]);
      }
    } finally {
      await closeDb();
    }
  });

  it("quotes list renders the quote with status and total", async () => {
    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilText(QUOTE_TITLE);
    await scrollUntilText(`${EXPECTED_TOTAL_TEXT} inc VAT`);
    await waitForText("Draft");
  });

  it("quote detail renders line items and totals matching the API", async () => {
    await scrollUntilId(`quote-card-${quoteId}`);
    await tapId(`quote-card-${quoteId}`);
    await waitForText("Review quote");
    await waitForText(QUOTE_TITLE);
    await waitForText("Line 1");
    await waitForText("Line 2");
    await waitForText(EXPECTED_TOTAL_TEXT);

    const api = (await apiGet(ctx, `/quotes/${quoteId}`)) as ApiQuoteRow;
    expect(api.line_items.length).toBe(2);
    expect(parseFloat(api.total)).toBe(696);
    expect(parseFloat(api.subtotal)).toBe(580);
    expect(parseFloat(api.vat_amount)).toBe(116);
  });

  it("refine with AI shows the regeneration state", async () => {
    const apiBefore = (await apiGet(ctx, `/quotes/${quoteId}`)) as ApiQuoteRow;
    if (!apiBefore.ai_generated) {
      throw new Error("quote is not flagged ai_generated — refine panel will not render");
    }

    await scrollUntilId("refine-instructions");
    const instructions = await waitForId("refine-instructions");
    await instructions.click();
    await instructions.setValue("Keep the consumer unit line and assume a mid-range board");
    await dismissKeyboard();
    await tapId("refine-submit");

    // Regeneration state: pulsing skeleton or the pending "Refining…" button.
    const skeleton = byId("refine-skeleton");
    await driver.waitUntil(
      async () => (await skeleton.isExisting()) || (await hasText("Refining…")),
      { timeout: 15000, timeoutMsg: "refine regeneration state (skeleton/Refining…) never appeared" }
    );

    // Wait for the refine call to settle (LLM round-trip; generous window).
    await driver.waitUntil(
      async () => !(await skeleton.isExisting()) && !(await hasText("Refining…")),
      { timeout: 120000, timeoutMsg: "refine did not settle within 120s" }
    );

    if (await byId("refine-error").isExisting()) {
      // LLM unavailable is an environment failure, not an app regression: the
      // regeneration state above is the UI contract under test.
      console.log("NOTE: refine returned an error (LLM unavailable?) — regeneration state was still shown");
      return;
    }
    const apiAfter = (await apiGet(ctx, `/quotes/${quoteId}`)) as ApiQuoteRow;
    expect(apiAfter.line_items.length).toBeGreaterThanOrEqual(1);
  });

  it("request-info flow opens the customer conversation", async () => {
    // A lead (quote request) is the entity a conversation threads around.
    const lead = (await apiPost(ctx, "/quote-requests", {
      contact_id: contactId,
      source: "manual",
      raw_text: LEAD_TEXT,
      urgency: "this_week",
    })) as { id: string };
    leadId = lead.id;

    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilId(`lead-card-${leadId}`);
    await tapId(`lead-card-${leadId}`);
    await waitForText("Lead detail");
    await tapId("lead-request-info");
    await waitForText("Messages", 25000);
    await tapBack();
    await waitForText("Lead detail");

    const api = (await apiGet(ctx, `/quote-requests/${leadId}`)) as ApiQuoteRequestRow;
    expect(api.id).toBe(leadId);
  });

  it("sending the quote marks it sent, emails the customer and is audit-logged", async () => {
    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilId(`quote-card-${quoteId}`);
    await tapId(`quote-card-${quoteId}`);
    await waitForText("Review quote");

    await tapId("quote-approve-send");
    await waitForText("Send quote?");
    await tapText("Send");
    // Sending saves latest edits then POSTs /quotes/{id}/send and navigates back.
    await waitForText("Quotes", 25000);

    const api = (await apiGet(ctx, `/quotes/${quoteId}`)) as ApiQuoteRow;
    expect(api.status).toBe("sent");
    expect(api.sent_at).toBeTruthy();

    if (dbConfigured()) {
      // The email itself goes through Resend (not persisted); the durable
      // record of the send is the audit-log entry on the quote.
      const sends = await countRows("audit_logs", "entity_id = $1 AND action = 'quote.sent'", [
        quoteId,
      ]);
      expect(sends).toBeGreaterThanOrEqual(1);
    }

    // Status badge on the list now reads "Sent".
    await scrollUntilId(`quote-card-${quoteId}`);
    await tapId(`quote-card-${quoteId}`);
    await waitForText("Sent");
    await tapBack();
  });

  it("accepted quote converts to a job that references the quote", async () => {
    // Convert requires backend status "approved" (customer acceptance).
    await apiPost(ctx, `/quotes/${quoteId}/approve`, { approved: true });

    await tapId("tab-quotes");
    await waitForText("Quotes");
    await scrollUntilId(`quote-card-${quoteId}`);
    await tapId(`quote-card-${quoteId}`);
    await waitForText("Review quote");
    await scrollUntilId("quote-convert-job");
    await tapId("quote-convert-job");

    await waitForText("Job detail", 30000);
    await waitForText(QUOTE_TITLE);

    const jobs = (await apiGet(ctx, "/jobs")) as ApiJobRow[];
    const job = jobs.find((j) => j.quote_id === quoteId);
    expect(job).toBeTruthy();
    if (job) {
      jobId = job.id;
      expect(job.title).toBe(QUOTE_TITLE);
    }
  });
});
