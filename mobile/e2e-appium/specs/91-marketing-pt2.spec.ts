/**
 * MARKETING — part 2 (recorded on device, build 12+, prod backend).
 *
 * Precondition (handled in `before` via the production API):
 *   - Sarah Thompson's sent quote is accepted (so the trade app can show
 *     quote → job conversion).
 *   - David Whitfield's job (EV charger) is rescheduled to today so it
 *     appears on the trade calendar for the recordings.
 *
 * Clips produced:
 *   04-job-management   — trade: accepted quote → Convert to job →
 *                         job detail (CONFIRMED, customer, address) →
 *                         calendar with bookings
 *   05-one-touch-invoice— trade: open today's job → start → complete →
 *                         add invoice line → Create & send invoice →
 *                         invoice detail (SENT) → mark paid
 *
 * Run (same env vars as part 1; MTP_API_BASE may be overridden):
 *   pnpm exec wdio run wdio.conf.ts --spec specs/91-marketing-pt2.spec.ts
 */
import { loginAsTrade } from "../helpers/auth";
import {
  dismissKeyboard,
  handlePermissionAlert,
  swipeUp,
  tapId,
  textElContains,
  waitForId,
  waitForText,
} from "../helpers/ui";
import {
  abortClip,
  scrollToIdAndTap,
  startClip,
  stopClip,
  tapNameContains,
  typeSlowly,
} from "../demo/recorder";

const API = process.env.MTP_API_BASE ?? "https://api-production-65db.up.railway.app";
const TID = "7b83ef32-7494-4a73-b6e2-9bdc67c33d22";
const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";
const SARAH_EMAIL = "sarah.thompson@example.com";
const SARAH_PASSWORD = "Homeowner26!";

async function apiJson(
  method: string,
  path: string,
  body: unknown,
  token?: string
): Promise<Record<string, unknown> | Record<string, unknown>[]> {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}`, "X-Tenant-ID": TID } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} → ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
  return (await res.json()) as Record<string, unknown> | Record<string, unknown>[];
}

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M2: marketing clips — part 2", () => {
  before(function () {
    this.timeout(0);
  });

  before(async () => {
    // Accept Sarah's most recent sent quote as the customer.
    // Accept both wire casings: /customer/login returns camelCase
    // accessToken; some other endpoints use access_token.
    const cust = (await apiJson("POST", "/customer/login", {
      slug: "hartley-electrical",
      email: SARAH_EMAIL,
      password: SARAH_PASSWORD,
    })) as { accessToken?: string; access_token?: string };
    const custToken = cust.accessToken ?? cust.access_token;
    if (!custToken) throw new Error("customer login returned no token");
    const quotes = (await apiJson("GET", "/customer/quotes", undefined, custToken)) as Array<{
      id: string;
      status: string;
      title?: string;
    }>;
    const sent = quotes.find((q) => q.status === "sent");
    if (!sent) throw new Error("no sent customer quote to accept — run part 1 first");
    await apiJson("POST", `/customer/quotes/${sent.id}/accept`, {
      preferred_dates: ["2026-09-16"],
    }, custToken);
    console.log(`[setup] accepted customer quote ${sent.id}`);

    // Move David's EV charger job to today so it shows on the calendar.
    const tom = (await apiJson("POST", "/auth/token", {
      email: TOM_EMAIL,
      password: TOM_PASSWORD,
    })) as { access_token: string };
    const jobs = (await apiJson("GET", "/jobs", undefined, tom.access_token)) as Array<{
      id: string;
      title?: string;
      status: string;
    }>;
    const evJob = jobs.find((j) => (j.title ?? "").toLowerCase().includes("ev charger"));
    if (!evJob) throw new Error("EV charger job not found — seed data missing");
    const today = new Date();
    const iso = (h: number) =>
      `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
        today.getDate()
      ).padStart(2, "0")}T${String(h).padStart(2, "0")}:00:00`;
    await apiJson("PATCH", `/jobs/${evJob.id}`, {
      scheduled_start: iso(13),
      scheduled_end: iso(17),
    }, tom.access_token);
    console.log(`[setup] rescheduled job ${evJob.id} to today`);
  });

  it("04-job-management", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);

    await startClip("04-job-management");
    await tapId("tab-quotes");
    await waitForText("Quotes");
    await driver.pause(1500);
    // Sarah's accepted quote card → open it.
    await textElContains("Sarah Thompson").waitForExist({ timeout: 15000 });
    await textElContains("Sarah Thompson").click();
    await waitForId("quote-line-description-0", 20000);
    await driver.pause(2000);
    await scrollToIdAndTap("quote-convert-job");
    await waitForText("Job detail", 20000);
    await textElContains("CONFIRMED").waitForExist({ timeout: 15000 });
    await driver.pause(3000);
    await swipeUp();
    await driver.pause(2000);
    await tapId("tab-calendar");
    await waitForText("Calendar", 15000);
    await driver.pause(3000);
    await stopClip("04-job-management");
  });

  it("05-one-touch-invoice", async () => {
    await startClip("05-one-touch-invoice");
    await tapId("tab-calendar");
    await waitForText("Calendar", 15000);
    await driver.pause(1500);
    // Today's EV charger booking.
    await textElContains("EV charger").waitForExist({ timeout: 15000 });
    await textElContains("EV charger").click();
    await waitForText("Job detail", 20000);
    await driver.pause(2000);
    await tapId("job-start");
    await textElContains("IN PROGRESS").waitForExist({ timeout: 15000 });
    await driver.pause(1500);
    await tapId("job-complete");
    await textElContains("COMPLETED").waitForExist({ timeout: 15000 });
    await driver.pause(1500);

    // Invoice items section: add one line, watch the live total, then
    // create & send in one tap.
    await scrollToIdAndTap("job-add-variation");
    const desc = driver.$(
      '-ios predicate string:name CONTAINS[c] "job-invoice-description"'
    );
    await desc.waitForExist({ timeout: 15000 });
    await typeSlowly(desc, "7kW EV charger — install, certification and DNO notification");
    const amount = driver.$(
      '-ios predicate string:name CONTAINS[c] "job-invoice-amount"'
    );
    await amount.waitForExist({ timeout: 15000 });
    await typeSlowly(amount, "1240");
    // The numeric keyboard covers the footer button — close it before the
    // create tap or the tap lands on the keyboard.
    await dismissKeyboard();
    await driver.pause(1500);
    await textElContains("Create & send invoice").waitForExist({ timeout: 15000 });
    await textElContains("Create & send invoice").click();

    // Invoice detail: SENT badge, total, line items.
    await waitForId("invoice-total", 20000);
    await driver.pause(3000);
    await swipeUp();
    await driver.pause(2000);
    await tapId("invoice-mark-paid");
    await textElContains("Payment received").waitForExist({ timeout: 15000 });
    await driver.pause(2500);
    await stopClip("05-one-touch-invoice");
  });
});
