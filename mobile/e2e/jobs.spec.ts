import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  fill,
  loginAsTradeOwner,
  seedScheduledJob,
  tap,
  Tenant,
  waitForJob,
  waitText,
} from "./helpers";

// Job creation, quote→job conversion and job-detail editing. All quotes/jobs
// are seeded over the API in beforeAll — no live LLM generation involved.

test.describe.serial("J — Job create, convert & detail editing", () => {
  let tenant: Tenant;
  let ownerId: string;
  let detailJob: { id: string; title: string };
  // Approved quote with 6 labour hours — drives the N15/N18 prefill checks.
  let hourQuote: { id: string; title: string };
  // Second approved quote — converted in place by the web button (N23).
  let convertQuote: { id: string; title: string };

  test.beforeAll(async () => {
    tenant = await createTestTenant("jobs");

    const users = (await api(tenant, "/users")) as Array<{
      id: string;
      full_name: string;
      tenant_id: string;
    }>;
    // GET /users scopes by RLS only; the local e2e stack connects as a
    // superuser (RLS no-op), so filter to this tenant explicitly.
    ownerId = users.find((u) => u.tenant_id === tenant.tenantId)!.id;

    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const scheduledStart = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00:00`;
    detailJob = await seedScheduledJob(tenant, {
      title: "E2E Assignee job",
      scheduledStart,
    });

    const seedApprovedQuote = async (
      title: string,
      email: string,
      phone: string
    ): Promise<{ id: string; title: string }> => {
      const contact = await api(tenant, "/contacts", {
        method: "POST",
        body: {
          name: "E2E Jobs Customer",
          email,
          phone,
          postcode: "SK8 3NJ",
          address: "3 E2E Road, Stockport",
        },
      });
      const quote = await api(tenant, "/quotes", {
        method: "POST",
        body: {
          contact_id: contact.id,
          title,
          line_items: [
            { description: "Labour — installation", quantity: 6, unit_price: 65, unit: "hours" },
          ],
          vat_rate: 0.2,
        },
      });
      await api(tenant, `/quotes/${quote.id}/approve`, {
        method: "POST",
        body: { approved: true },
      });
      return quote;
    };

    hourQuote = await seedApprovedQuote("E2E Hourly quote", "jobs-hourly@e2e.example.com", "07700 900331");
    convertQuote = await seedApprovedQuote("E2E Convert quote", "jobs-convert@e2e.example.com", "07700 900332");
  });

  test("N9: owner creates a job with an inline new customer", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto("/(trade)/job/new", { waitUntil: "networkidle" });
    await waitText(page, "New job");

    await tap(page, "job-create-customer-new");
    await fill(page, "job-create-title", "E2E Inline-customer job");
    await fill(page, "job-create-new-customer-name", "E2E Inline Customer");
    await fill(page, "job-create-new-customer-phone", "07700 900222");
    await fill(page, "job-create-new-customer-email", "inline-customer@e2e.example.com");
    await fill(page, "job-create-new-customer-postcode", "SK8 3NJ");
    await tap(page, "job-create-submit");

    await waitText(page, "Job detail", 30000);
    const job = (await waitForJob(tenant, "E2E Inline-customer job", undefined, 30000)) as {
      customer: { name: string };
    };
    expect(job.customer.name).toBe("E2E Inline Customer");
  });

  test("N11: assignee chips and notes are editable on job detail", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/job/${detailJob.id}`, { waitUntil: "networkidle" });
    await waitText(page, "Job detail");

    await tap(page, "job-assignee-edit");
    await tap(page, `job-assignee-${ownerId}`);
    await expect(page.locator('[data-testid="job-assignee-name"]')).toHaveText(tenant.adminName, {
      timeout: 20000,
    });

    await fill(page, "job-notes-input", "E2E notes — key safe 9988");
    await tap(page, "job-notes-save");

    // Both edits persist server-side.
    const deadline = Date.now() + 30000;
    let saved: { assigned_user_id: string | null; notes: string | null } | undefined;
    while (Date.now() < deadline) {
      const jobs = (await api(tenant, "/jobs")) as Array<{
        id: string;
        assigned_user_id: string | null;
        notes: string | null;
      }>;
      const found = jobs.find((j) => j.id === detailJob.id);
      if (found && found.assigned_user_id === ownerId && found.notes?.includes("key safe 9988")) {
        saved = found;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    expect(saved, "assignee + notes did not persist").toBeTruthy();
  });

  test("N15: job create from an approved quote prefills duration from labour hours", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/job/new?quoteId=${hourQuote.id}`, { waitUntil: "networkidle" });
    await waitText(page, "New job");

    // The prefill runs once the quotes query resolves; wait for the values.
    await expect(page.locator('[data-testid="job-create-duration"]')).toHaveValue("6", {
      timeout: 30000,
    });
    await expect(page.locator('[data-testid="job-create-title"]')).toHaveValue(hourQuote.title);
    await waitText(page, "from the selected quote");
  });

  test("N18: selecting a quote prefills customer/duration and converts to a job", async ({
    page,
  }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto("/(trade)/job/new", { waitUntil: "networkidle" });
    await waitText(page, "New job");

    await fill(page, "job-create-quote-search", "E2E Hourly");
    await tap(page, `job-create-quote-option-${hourQuote.id}`);
    await waitText(page, "from the selected quote");
    await expect(page.locator('[data-testid="job-create-duration"]')).toHaveValue("6", {
      timeout: 30000,
    });

    await tap(page, "job-create-submit");
    await waitText(page, "Job detail", 30000);
    const job = await waitForJob(tenant, hourQuote.title, undefined, 30000);
    expect(job).toBeTruthy();
  });

  test("N23: web convert-to-job button converts and navigates to the job", async ({ page }) => {
    await loginAsTradeOwner(page, tenant);
    await page.goto(`/(trade)/quote/${convertQuote.id}`, { waitUntil: "networkidle" });
    await waitText(page, "Review quote");

    await tap(page, "quote-convert-job");
    await waitText(page, "Job detail", 30000);
    const job = await waitForJob(tenant, convertQuote.title, undefined, 30000);
    expect(job).toBeTruthy();
  });
});
