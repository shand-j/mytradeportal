/**
 * 16 — Trade calendar: week renders, create a job ("appointment") via the
 * "+ New job" UI, assert it persists via the API, and that the booking shows
 * on the calendar.
 *
 * Note: the app has no month view — the trade calendar is a day/week grid of
 * *jobs* (POST /jobs, GET /jobs); the trade /appointments endpoint is probed
 * too so both surfaces are exercised.
 */
import { relaunchApp } from "../helpers/app";
import { loginAsTrade } from "../helpers/auth";
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
import {
  swipeUp,
  tapId,
  tapText,
  textElContains,
  waitForId,
  waitForText,
  dismissKeyboard,
} from "../helpers/ui";

const tag = Date.now().toString(36);
const JOB_TITLE = `E2E Calendar job ${tag}`;
const JOB_NOTES = `E2E notes ${tag}`;

function todayIsoDate(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** First element whose accessibility id starts with the given prefix. */
async function firstByIdPrefix(
  prefix: string
): Promise<WebdriverIO.Element | null> {
  const els = await (await $$(`-ios predicate string:name BEGINSWITH '${prefix}'`)).getElements();
  return els.length > 0 ? els[0] : null;
}

async function scrollUntilId(id: string, timeoutMs = 20000) {
  const el = $(`~${id}`);
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

describe("16: trade calendar", () => {
  if (!tradeCredsConfigured()) {
    console.log("SKIP: E2E_TRADE_EMAIL/E2E_TRADE_PASSWORD not set");
    return;
  }

  let ctx: ApiTenantContext | null = null;
  let jobCreated = false;

  afterEach(async function () {
    const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
    if (state !== "failed") return;
    const fs = await import("node:fs");
    try {
      fs.writeFileSync(`/tmp/e2e-debug-16-${Date.now()}.xml`, await driver.getPageSource());
    } catch {
      /* keep the original error */
    }
  });

  before(async () => {
    await loginAsTrade(TRADE_EMAIL, TRADE_PASSWORD);
    ctx = await loginTradeApi();
  });

  after(async () => {
    if (jobCreated && dbConfigured()) {
      await deleteTestData("title = $1", [JOB_TITLE]);
    }
    await closeDb();
  });

  it("renders the week calendar (day strip, bookings, week view)", async () => {
    await relaunchApp();
    await tapId("tab-calendar");
    await waitForText("Calendar");
    await waitForText("Bookings");
    await waitForId("calendar-today");
    await waitForId("calendar-new-job");
    // Week view renders the 7-day header + the "N bookings this week" caption.
    await tapId("calendar-week");
    const caption = textElContains("bookings this week");
    await caption.waitForExist({ timeout: 15000 });
    await tapId("calendar-day");
    await driver.pause(400);
  });

  it("creates a job via + New job and persists it via the API", async () => {
    await tapId("calendar-new-job");
    await waitForId("job-create-title");

    // A job needs an existing customer contact; pick the first one listed.
    const contact = await firstByIdPrefix("job-create-contact-");
    if (!contact) {
      console.log("SKIP: no customer contacts available to attach the job to");
      return;
    }

    const titleField = await waitForId("job-create-title");
    await titleField.click();
    await titleField.setValue(JOB_TITLE);
    await contact.click();

    const dateField = await waitForId("job-create-date");
    await dateField.click();
    await dateField.setValue(todayIsoDate());
    const timeField = await waitForId("job-create-time");
    await timeField.click();
    await timeField.setValue("09:00");
    const notesField = await waitForId("job-create-notes");
    await notesField.click();
    await notesField.setValue(JOB_NOTES);
    await dismissKeyboard();
    // Multiline notes: Return inserts "\n" and the keyboard stays up,
    // covering the submit button. Defocus, then reveal and tap submit.
    await tapText("Title", 8000);
    await driver.pause(400);
    await scrollUntilId("job-create-submit");
    await tapId("job-create-submit", 25000);
    // Creation routes to the job detail screen.
    await waitForText("Job detail", 25000);
    await waitForText(JOB_TITLE, 15000);
    jobCreated = true;

    const jobs = (await apiGet(ctx as ApiTenantContext, "/jobs")) as Array<
      Record<string, unknown>
    >;
    const job = jobs.find((j) => j.title === JOB_TITLE);
    expect(job).toBeTruthy();
    expect(String((job as Record<string, unknown>).description)).toBe(JOB_NOTES);
    expect(String((job as Record<string, unknown>).scheduled_start)).toContain(todayIsoDate());

    // The trade appointments endpoint is reachable and returns a list.
    const appointments = (await apiGet(ctx as ApiTenantContext, "/appointments")) as unknown;
    expect(Array.isArray(appointments)).toBe(true);
  });

  it("shows the booking on the calendar", async () => {
    await tapId("tab-calendar");
    await driver.pause(600);
    // Job date is today, which is the default selected day. The booking row
    // collapses into one element ("08:00, <title>, <customer> · <postcode>").
    const booking = textElContains(JOB_TITLE);
    await booking.waitForExist({ timeout: 25000 });
    if (dbConfigured()) {
      const n = await countRows("jobs", "title = $1", [JOB_TITLE]);
      expect(n).toBe(1);
    }
  });
});
