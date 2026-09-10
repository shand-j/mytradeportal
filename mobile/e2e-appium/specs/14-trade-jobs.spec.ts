/**
 * Trade jobs:
 *  - manual job creation from the calendar screen persists (title, customer,
 *    schedule, notes)
 *  - job detail drives the status lifecycle start → in_progress → completed,
 *    cross-checked against the API after each transition
 *  - the job appears in the calendar bookings list and opens its detail
 *
 * A dedicated contact is created via the API with a unique tag so the job
 * create form has a known customer row to pick; everything is cleaned up in
 * the after hook.
 */
import {
  apiGet,
  closeDb,
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
  tapId,
  tapText,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";
import { API_BASE } from "../helpers/env";

const TAG = Date.now().toString(36);
const CUSTOMER_NAME = `E2E Job Customer ${TAG}`;
const CUSTOMER_EMAIL = `e2e-job-${TAG}@example.com`;
const JOB_TITLE = `E2E Job ${TAG}`;
const JOB_NOTES = `E2E notes ${TAG}: key safe code 1234, park on the drive.`;

function futureDate(offsetDays: number): string {
  const d = new Date(Date.now() + offsetDays * 86400000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

interface ApiContactRow {
  id: string;
  email: string | null;
}

interface ApiJobRow {
  id: string;
  title: string;
  status: string;
  scheduled_start: string | null;
  completed_at: string | null;
  quote_id: string | null;
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

type SettableElement = { click(): Promise<unknown>; setValue(value: string): Promise<unknown> };

async function setValue(el: SettableElement, value: string) {
  await el.click();
  await el.setValue(value);
  await dismissKeyboard();
}

describe("trade jobs", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext;
  let contactId = "";
  let jobId = "";
  // Today so the job lands in the calendar's default day view.
  const jobDate = futureDate(0);

  afterEach(async function () {
    const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
    if (state !== "failed") return;
    const fs = await import("node:fs");
    try {
      const num = 14;
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
      phone: "07111222333",
      postcode: "B3 1AA",
    })) as ApiContactRow;
    contactId = contact.id;
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
  });

  after(async () => {
    if (!dbConfigured()) {
      console.log("NOTE: MTP_DB_URL not set — skipping DB cleanup for", JOB_TITLE);
      await closeDb();
      return;
    }
    try {
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

  it("manual job creation persists title, customer and schedule", async () => {
    await tapId("tab-calendar");
    await waitForText("Calendar");
    await tapId("calendar-new-job");
    await waitForText("New job");

    await setValue(await waitForId("job-create-title"), JOB_TITLE);
    await scrollUntilId(`job-create-contact-${contactId}`);
    await tapId(`job-create-contact-${contactId}`);
    await setValue(await waitForId("job-create-date"), jobDate);
    await setValue(await waitForId("job-create-time"), "09:30");
    await scrollUntilId("job-create-notes");
    await setValue(await waitForId("job-create-notes"), JOB_NOTES);
    // The notes field is multiline: Return inserts "\n" instead of closing
    // the keyboard, so the submit button stays hidden behind it. Defocus by
    // tapping the form's Title label, then reveal the submit button.
    await tapText("Title", 8000);
    await driver.pause(400);
    await scrollUntilId("job-create-submit");
    await tapId("job-create-submit");
    await waitForText("Job detail", 25000);
    await waitForText(JOB_TITLE);
    await waitForText("CONFIRMED");

    const jobs = (await apiGet(ctx, "/jobs")) as ApiJobRow[];
    const job = jobs.find((j) => j.title === JOB_TITLE);
    expect(job).toBeTruthy();
    if (!job) return;
    jobId = job.id;
    expect(job.status).toBe("scheduled");
    expect(job.scheduled_start).toBeTruthy();
    expect(String(job.scheduled_start).slice(0, 10)).toBe(jobDate);
  });

  it("job detail transitions start → complete, persisted each step", async () => {
    await tapId("job-start");
    await waitForText("IN PROGRESS", 25000);
    let api = (await apiGet(ctx, `/jobs/${jobId}`)) as ApiJobRow;
    expect(api.status).toBe("in_progress");

    await tapId("job-complete");
    await waitForText("COMPLETED", 25000);
    api = (await apiGet(ctx, `/jobs/${jobId}`)) as ApiJobRow;
    expect(api.status).toBe("completed");
    expect(api.completed_at).toBeTruthy();
  });

  it("completed job shows the invoice-creation surface", async () => {
    await waitForId("job-create-invoice");
    await waitForText("Invoice items");
  });

  it("job appears in the calendar bookings list and opens its detail", async () => {
    await tapId("tab-calendar");
    await waitForText("Calendar");
    await driver.pause(500);
    await waitForId(`booking-${jobId}`, 15000);
    await tapId(`booking-${jobId}`);
    await waitForText("Job detail");
    await waitForText(JOB_TITLE);
  });
});
