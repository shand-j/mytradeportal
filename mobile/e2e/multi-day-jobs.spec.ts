import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  loginAsTradeOwner,
  seedContact,
  tap,
  Tenant,
  waitText,
} from "./helpers";

// Multi-day jobs (G27, P1): a quote carrying estimated working hours beyond
// the tenant's single-day working hours is flagged ``is_multi_day``; the
// scheduler recommends the earliest start where the whole working-day block
// sequence fits; converting to a job caps day 1 at the daily hours and books
// the remaining consecutive working-day blocks as appointments; rescheduling
// the job shifts every block by the same delta. All quotes are seeded over
// the API with explicit ``estimated_hours`` — no live LLM involved.
//
// The tenant is pinned to 09:00-17:00 (8h/day), Monday-Friday, so the specs
// can assert weekend skipping and per-day caps deterministically.

const pad = (n: number) => String(n).padStart(2, "0");
const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
/** Next date whose weekday (Mon=0) matches, strictly after `from`. */
function nextWeekday(weekday: number, from = new Date()): Date {
  const d = new Date(from);
  d.setDate(d.getDate() + 1);
  while (d.getDay() !== weekday) d.setDate(d.getDate() + 1);
  return d;
}
const nextMonday = () => nextWeekday(1);
/** Weekday ints of a YYYY-MM-DD string (JS getDay: Sun=0, Mon=1 … Sat=6). */
const weekdayOf = (iso: string) => new Date(`${iso}T12:00:00`).getDay();

type Quote = {
  id: string;
  title: string;
  estimated_hours: string | number | null;
  is_multi_day: boolean;
  status: string;
};

type Suggestion = {
  start_date: string;
  start_time: string;
  days: Array<{ date: string; hours: number }>;
  is_multi_day: boolean;
};

test.describe.serial("R — Multi-day job planning", () => {
  let tenant: Tenant;
  let contactId: string;
  // 14h quote (8h daily → 2 blocks); converted in the convert test.
  let bigQuote: Quote;
  // Second 14h quote for the job-create UI test.
  let uiQuote: Quote;
  // The job created from bigQuote, reused by the reschedule test.
  let jobId: string;

  test.beforeAll(async () => {
    tenant = await createTestTenant("multiday");

    // Pin the working week: 8 working hours/day, Monday-Friday only.
    await api(tenant, "/tenants/me", {
      method: "PATCH",
      body: {
        settings: {
          working_day_start: "09:00",
          working_day_end: "17:00",
          working_days: [0, 1, 2, 3, 4],
        },
      },
    });

    contactId = (await seedContact(tenant, { name: "E2E Multi-day Customer" })).id as string;

    const seedQuote = async (title: string, estimatedHours: number): Promise<Quote> => {
      const quote = (await api(tenant, "/quotes", {
        method: "POST",
        body: {
          contact_id: contactId,
          title,
          estimated_hours: estimatedHours,
          line_items: [
            { description: "Labour — rewire", quantity: estimatedHours, unit_price: 55, unit: "hours" },
          ],
        },
      })) as Quote;
      await api(tenant, `/quotes/${quote.id}/approve`, { method: "POST", body: { approved: true } });
      return quote;
    };

    bigQuote = await seedQuote("E2E 14-hour rewire", 14);
    uiQuote = await seedQuote("E2E UI multi-day rewire", 14);
  });

  test("G27: quotes exceeding the daily working hours are flagged is_multi_day", async () => {
    expect(Number(bigQuote.estimated_hours)).toBe(14);
    expect(bigQuote.is_multi_day).toBe(true);

    // Control: a 6-hour quote fits inside one 8-hour day.
    const small = (await api(tenant, "/quotes", {
      method: "POST",
      body: {
        contact_id: contactId,
        title: "E2E 6-hour socket run",
        estimated_hours: 6,
        line_items: [{ description: "Labour", quantity: 6, unit_price: 55, unit: "hours" }],
      },
    })) as Quote;
    expect(Number(small.estimated_hours)).toBe(6);
    expect(small.is_multi_day).toBe(false);

    // The flag is derived on reads too, not just at creation.
    const reread = (await api(tenant, `/quotes/${bigQuote.id}`)) as Quote;
    expect(reread.is_multi_day).toBe(true);
  });

  test("G27: suggest-schedule recommends the earliest fitting slot, capped per day", async () => {
    const suggestion = (await api(
      tenant,
      `/jobs/suggest-schedule?quote_id=${bigQuote.id}`
    )) as Suggestion;

    expect(suggestion.is_multi_day).toBe(true);
    expect(suggestion.start_time).toBe("09:00");
    // 14h at 8h/day → exactly two blocks.
    expect(suggestion.days.length).toBe(2);
    for (const day of suggestion.days) {
      expect(day.hours).toBeLessThanOrEqual(8);
      // Monday-Friday tenant (JS getDay: Mon=1 … Fri=5, Sat=6, Sun=0).
      expect([1, 2, 3, 4, 5]).toContain(weekdayOf(day.date));
    }
    // Blocks are consecutive working days (8h then the 6h remainder).
    expect(suggestion.days[0].hours).toBe(8);
    expect(suggestion.days[1].hours).toBeCloseTo(6, 5);
    const gap =
      (new Date(`${suggestion.days[1].date}T12:00:00`).getTime() -
        new Date(`${suggestion.days[0].date}T12:00:00`).getTime()) /
      86_400_000;
    expect(gap === 1 || gap === 3).toBe(true); // adjacent, or Thu→Mon over a weekend

    // A full-day booking on the suggested start pushes the recommendation out:
    // the whole block sequence must fit, so the busy day can no longer be day 1.
    await api(tenant, "/jobs", {
      method: "POST",
      body: {
        contact_id: contactId,
        title: "E2E Calendar blocker",
        scheduled_start: `${suggestion.start_date}T09:00:00`,
        scheduled_end: `${suggestion.start_date}T17:00:00`,
      },
    });
    const moved = (await api(
      tenant,
      `/jobs/suggest-schedule?quote_id=${bigQuote.id}`
    )) as Suggestion;
    expect(moved.start_date).not.toBe(suggestion.start_date);
    for (const day of moved.days) {
      expect(day.hours).toBeLessThanOrEqual(8);
    }

    // The plain `hours=` form agrees with the quote-derived volume.
    const byHours = (await api(tenant, "/jobs/suggest-schedule?hours=20")) as Suggestion;
    expect(byHours.is_multi_day).toBe(true);
    expect(byHours.days.length).toBe(3); // 8 + 8 + 4
  });

  test("G27: converting caps day 1 at the daily hours and books the rest as appointments", async () => {
    const monday = isoDay(nextMonday());
    const start = `${monday}T09:00:00`;
    const job = (await api(tenant, `/quotes/${bigQuote.id}/convert-to-job`, {
      method: "POST",
      body: { scheduled_start: start, scheduled_end: `${monday}T23:00:00` },
    })) as { id: string; scheduled_start: string; scheduled_end: string };
    jobId = job.id;

    // Day 1 is capped at the 8 working hours, not the requested 14.
    expect(job.scheduled_start).toBe(start);
    expect(job.scheduled_end).toBe(`${monday}T17:00:00`);

    // The remaining 6h land on the next working day as a linked appointment.
    const appointments = (await api(tenant, "/appointments")) as Array<{
      id: string;
      job_id: string;
      title: string;
      start_at: string;
      end_at: string;
    }>;
    const blocks = appointments.filter((a) => a.job_id === job.id);
    expect(blocks.length).toBe(1);
    expect(blocks[0].title).toContain("day 2 of 2");
    const tuesday = isoDay(new Date(new Date(`${monday}T12:00:00`).getTime() + 86_400_000));
    expect(blocks[0].start_at).toBe(`${tuesday}T09:00:00`);
    const hours =
      (new Date(blocks[0].end_at).getTime() - new Date(blocks[0].start_at).getTime()) / 3_600_000;
    expect(hours).toBeCloseTo(6, 5);
  });

  test("G27: the job-create screen flags the multi-day quote and offers the earliest fit", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/job/new?quoteId=${uiQuote.id}`, { waitUntil: "networkidle" });
    await waitText(page, "New job");

    // Duration prefills from the quote's estimated hours.
    await expect(page.locator('[data-testid="job-create-duration"]')).toHaveValue("14", {
      timeout: 30_000,
    });

    // The multi-day badge names the block count once the suggestion resolves.
    await expect(page.locator('[data-testid="job-create-multiday"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('[data-testid="job-create-multiday"]')).toContainText("Multi-day job");
    await expect(page.locator('[data-testid="job-create-multiday"]')).toContainText(
      "spans 2 working days"
    );

    // The scheduler recommendation is one tap away.
    const suggestion = page.locator('[data-testid="job-create-schedule-suggestion"]');
    await expect(suggestion).toBeVisible({ timeout: 30_000 });
    await expect(suggestion).toContainText("Earliest fit:");
    await expect(suggestion).toContainText("+ 1 more day");

    // Tapping it fills the date/time fields with the recommended slot.
    await tap(page, "job-create-schedule-suggestion");
    const apiSuggestion = (await api(
      tenant,
      `/jobs/suggest-schedule?quote_id=${uiQuote.id}`
    )) as Suggestion;
    await expect(page.locator('[data-testid="job-create-date"]')).toHaveValue(
      apiSuggestion.start_date
    );
    await expect(page.locator('[data-testid="job-create-time"]')).toHaveValue("09:00");

    // Submitting through the UI applies the same split server-side.
    await tap(page, "job-create-submit");
    await waitText(page, "Job detail", 30_000);
    const jobs = (await api(tenant, "/jobs")) as Array<{ id: string; quote_id: string }>;
    const created = jobs.find((j) => j.quote_id === uiQuote.id);
    expect(created, "job-create did not convert the quote").toBeTruthy();
    const appointments = (await api(tenant, "/appointments")) as Array<{
      job_id: string;
      title: string;
    }>;
    const uiBlocks = appointments.filter((a) => a.job_id === (created as { id: string }).id);
    expect(uiBlocks.length).toBe(1);
    expect(uiBlocks[0].title).toContain("day 2 of 2");
  });

  test("G27: rescheduling the job shifts every block appointment by the same delta", async () => {
    const appointmentsBefore = (await api(tenant, "/appointments")) as Array<{
      job_id: string;
      title: string;
      start_at: string;
      end_at: string;
    }>;
    const blockBefore = appointmentsBefore.find((a) => a.job_id === jobId);
    expect(blockBefore, "block appointment missing before reschedule").toBeTruthy();

    const current = (await api(tenant, `/jobs/${jobId}`)) as {
      scheduled_start: string;
      scheduled_end: string;
    };
    const shifted = new Date(new Date(current.scheduled_start).getTime() + 2 * 86_400_000);
    const newStart = `${isoDay(shifted)}T09:00:00`;
    const newEnd = `${isoDay(shifted)}T17:00:00`;

    await api(tenant, `/jobs/${jobId}`, {
      method: "PATCH",
      body: { scheduled_start: newStart, scheduled_end: newEnd },
    });

    const job = (await api(tenant, `/jobs/${jobId}`)) as {
      scheduled_start: string;
      scheduled_end: string;
    };
    expect(job.scheduled_start).toBe(newStart);
    expect(job.scheduled_end).toBe(newEnd);

    // The block moves by the job's own delta (+2 days), keeping its duration.
    // Schedule columns are naive local datetimes on the wire ("YYYY-MM-DDTHH:MM:SS"),
    // so shift the date part arithmetically instead of round-tripping through Date.
    const appointmentsAfter = (await api(tenant, "/appointments")) as Array<{
      job_id: string;
      title: string;
      start_at: string;
      end_at: string;
    }>;
    const blockAfter = appointmentsAfter.find((a) => a.job_id === jobId);
    expect(blockAfter, "block appointment missing after reschedule").toBeTruthy();
    const shiftDay = (raw: string, days: number): string => {
      const base = new Date(`${raw.slice(0, 10)}T12:00:00`);
      base.setDate(base.getDate() + days);
      return `${isoDay(base)}${raw.slice(10)}`;
    };
    expect(blockAfter!.start_at).toBe(shiftDay(blockBefore!.start_at, 2));
    expect(blockAfter!.end_at).toBe(shiftDay(blockBefore!.end_at, 2));
  });
});
