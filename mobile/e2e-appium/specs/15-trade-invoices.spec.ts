/**
 * Trade invoices:
 *  - invoices list renders with Outstanding/Paid summary cards
 *  - completing a job surfaces the invoice items form; "Create & send invoice"
 *    persists an invoice, marks it sent and emails the customer (the send is
 *    audit-logged; the email itself goes through Resend and is not persisted)
 *  - invoice detail total matches the API line items
 *  - send reminder re-notifies without changing status
 *  - mark-paid flips status to paid with a paid_at timestamp
 *
 * Setup creates a contact + scheduled job via the API (unique tag); the invoice
 * is created through the UI. Everything is deleted in the after hook.
 */
import {
  apiGet,
  closeDb,
  countRows,
  dbConfigured,
  deleteTestData,
  loginTradeApi,
  tradeCredsConfigured,
  TRADE_EMAIL,
  TRADE_PASSWORD,
  type ApiTenantContext,
} from "../helpers/api";
import { loginAsTrade } from "../helpers/auth";
import {
  byId,
  swipeUp,
  tapBack,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";
import { API_BASE } from "../helpers/env";

const TAG = Date.now().toString(36);
const CUSTOMER_NAME = `E2E Invoice Customer ${TAG}`;
const CUSTOMER_EMAIL = `e2e-invoice-${TAG}@example.com`;
const JOB_TITLE = `E2E Invoice Job ${TAG}`;
const LINE_DESCRIPTION = `E2E callout and repair ${TAG}`;
const LINE_AMOUNT = 120;

function todayAtNine(): string {
  const d = new Date();
  d.setHours(9, 0, 0, 0);
  return d.toISOString();
}

/** Same output as the app's formatMoneyGBP (Intl en-GB GBP). */
function gbp(amount: number): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(amount);
}

interface ApiContactRow {
  id: string;
  email: string | null;
}

interface ApiJobRow {
  id: string;
  title: string;
  status: string;
}

interface ApiInvoiceRow {
  id: string;
  job_id: string | null;
  status: string;
  total: string;
  subtotal: string;
  vat_amount: string;
  paid_at: string | null;
  line_items: Array<{ description: string; quantity: string; unit_price: string; total: string }>;
}

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

/** Text input located by the prefix of its testID (ids contain a timestamp). */
function inputByIdPrefix(prefix: string) {
  const escaped = prefix.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return $(`-ios predicate string:name CONTAINS "${escaped}"`);
}

type SettableElement = { click(): Promise<unknown>; setValue(value: string): Promise<unknown> };

async function setValue(el: SettableElement, value: string) {
  await el.click();
  await el.setValue(value);
  await dismissKeyboard();
}

describe("trade invoices", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let contactId = "";
  let jobId = "";
  let invoiceId = "";

  afterEach(async function () {
    const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
    if (state !== "failed") return;
    const fs = await import("node:fs");
    try {
      const num = 15;
      fs.writeFileSync(`/tmp/e2e-debug-${num}-${Date.now()}.xml`, await driver.getPageSource());
    } catch {
      /* keep the original error */
    }
  });

  before(async () => {
    ctx = await loginTradeApi();
    const contact = (await apiPost(ctx, "/contacts", {
      name: CUSTOMER_NAME,
      email: CUSTOMER_EMAIL,
      phone: "07444555666",
      postcode: "L1 8JQ",
    })) as ApiContactRow;
    contactId = contact.id;
    const job = (await apiPost(ctx, "/jobs", {
      contact_id: contactId,
      title: JOB_TITLE,
      description: "E2E invoice source job",
      scheduled_start: todayAtNine(),
    })) as ApiJobRow;
    jobId = job.id;
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    if (!dbConfigured()) {
      console.log("NOTE: MTP_DB_URL not set — skipping DB cleanup for", JOB_TITLE);
      await closeDb();
      return;
    }
    try {
      if (invoiceId) {
        await deleteTestData("invoice_id = $1", [invoiceId]);
        await deleteTestData("id = $1", [invoiceId]);
      }
      if (jobId) {
        await deleteTestData("job_id = $1", [jobId]);
        await deleteTestData("id = $1", [jobId]);
      }
      if (contactId) {
        await deleteTestData("contact_id = $1", [contactId]);
        await deleteTestData("email = $1", [CUSTOMER_EMAIL]);
        await deleteTestData("id = $1", [contactId]);
      }
    } finally {
      await closeDb();
    }
  });

  it("invoices list renders with Outstanding and Paid summary cards", async () => {
    await tapId("dashboard-more");
    await waitForText("Settings");
    // The settings row collapses into one element: "Invoices, Raise, track &
    // mark paid" — match it by substring, not exact label.
    const row = textElContains("Invoices");
    await row.waitForExist({ timeout: 15000 });
    await row.click();
    await waitForText("Invoices", 15000);
    await waitForText("Outstanding");
    await waitForText("Paid");
    await tapBack();
  });

  it("creates and sends an invoice from the completed job", async () => {
    // Complete on the backend (UI transitions are covered by the jobs spec) so
    // the job detail shows the invoice-items form.
    await apiPost(ctx, `/jobs/${jobId}/complete`);

    await tapId("tab-calendar");
    await waitForText("Calendar");
    await scrollUntilId(`booking-${jobId}`);
    await tapId(`booking-${jobId}`);
    await waitForText("Job detail");
    await waitForText("COMPLETED");

    await waitForId("job-add-variation");
    await tapId("job-add-variation");
    await setValue(await inputByIdPrefix("job-invoice-description"), LINE_DESCRIPTION);
    await setValue(await inputByIdPrefix("job-invoice-amount"), String(LINE_AMOUNT));
    // Defocus: the amount field keeps the keyboard up (Return does not close
    // it), which would swallow the tap on the create-invoice button below.
    await tapText("Invoice items", 8000);
    await driver.pause(400);
    await scrollUntilId("job-create-invoice");
    await tapId("job-create-invoice");
    // createAndSendInvoice persists the invoice and immediately marks it sent.
    await waitForId("invoice-total", 30000);
    await waitForText(LINE_DESCRIPTION);

    const invoices = (await apiGet(ctx, "/invoices")) as ApiInvoiceRow[];
    const invoice = invoices.find((i) => i.job_id === jobId);
    expect(invoice).toBeTruthy();
    if (!invoice) return;
    invoiceId = invoice.id;
    expect(invoice.status).toBe("sent");
    expect(parseFloat(invoice.subtotal)).toBe(LINE_AMOUNT);

    if (dbConfigured()) {
      // The email itself goes through Resend (not persisted); the durable
      // record of the send is the audit-log entry on the invoice.
      const sends = await countRows("audit_logs", "entity_id = $1 AND action = 'invoice.sent'", [
        invoiceId,
      ]);
      expect(sends).toBeGreaterThanOrEqual(1);
    }
  });

  it("invoice detail totals match the persisted line items", async () => {
    const invoice = (await apiGet(ctx, `/invoices/${invoiceId}`)) as ApiInvoiceRow;
    const subtotal = invoice.line_items.reduce(
      (sum, li) => sum + (parseFloat(li.quantity) || 0) * (parseFloat(li.unit_price) || 0),
      0
    );
    const vat = parseFloat(invoice.vat_amount);
    const total = parseFloat(invoice.total);
    expect(Math.abs(subtotal + vat - total)).toBeLessThan(0.01);

    const totalEl = await waitForId("invoice-total");
    expect(await totalEl.getText()).toBe(gbp(total));
    await waitForText("Line items");
    await waitForText(LINE_DESCRIPTION);
  });

  it("send reminder re-notifies the customer and keeps the status sent", async () => {
    await tapId("invoice-send-reminder");
    // A successful send closes the detail screen (onClose) — back on job detail.
    await waitForText("Job detail", 25000);

    const invoice = (await apiGet(ctx, `/invoices/${invoiceId}`)) as ApiInvoiceRow;
    expect(invoice.status).toBe("sent");

    if (dbConfigured()) {
      const sends = await countRows("audit_logs", "entity_id = $1 AND action = 'invoice.sent'", [
        invoiceId,
      ]);
      expect(sends).toBeGreaterThanOrEqual(2);
    }
  });

  it("mark-paid records payment and shows the paid banner", async () => {
    // Job detail now links the existing invoice; open the invoices list.
    await waitForId("job-view-invoice");
    await tapId("tab-dashboard");
    await waitForText("Dashboard");
    await tapId("dashboard-more");
    await waitForText("Settings");
    const invRow = textElContains("Invoices");
    await invRow.waitForExist({ timeout: 15000 });
    await invRow.click();
    await waitForText("Invoices", 15000);

    await scrollUntilId(`invoice-card-${invoiceId}`);
    await tapId(`invoice-card-${invoiceId}`);
    await waitForId("invoice-total");

    await tapId("invoice-mark-paid");
    await waitForId("invoice-paid-banner", 25000);
    await waitForText("Payment received");

    const invoice = (await apiGet(ctx, `/invoices/${invoiceId}`)) as ApiInvoiceRow;
    expect(invoice.status).toBe("paid");
    expect(invoice.paid_at).toBeTruthy();

    if (dbConfigured()) {
      const paids = await countRows("audit_logs", "entity_id = $1 AND action = 'invoice.paid'", [
        invoiceId,
      ]);
      expect(paids).toBeGreaterThanOrEqual(1);
    }
  });
});
