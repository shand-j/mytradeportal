import { test } from "@playwright/test";
import {
  api,
  apiRaw,
  createTestTenant,
  expect,
  seedContact,
  Tenant,
} from "./helpers";

// AI metadata contract (G34): a generated quote exposes ai_confidence,
// ai_warnings, ai_assumptions and retrieval_status, and every AI-drafted line
// uses a catalogue unit (ea/m/hr) — NEVER unit="job" (repeat regression: a
// user saw "1.5mm twin and earth cable, qty 200, unit=job").
//
// The unit contract is asserted without an LLM: POST /quotes accepts
// ai_generated line items directly (same seeding technique as the deployed
// write suite). The quote-level metadata only exists after a real generation
// pass (it lives in quote.extra_data["rag"]), so that half attempts
// POST /quotes/generate and skips cleanly when the target api has no LLM
// configured (the local dev api answers 503).

const CATALOGUE_UNITS = ["ea", "m", "hr"];

// The exact repeat-regression shape: bulk cable must be metre-priced, not
// quoted as a single "job".
const AI_LINES = [
  { description: "1.5mm twin and earth cable", quantity: 200, unit_price: 0.85, unit: "m", ai_generated: true },
  { description: "20A RCBO consumer unit", quantity: 1, unit_price: 120, unit: "ea", ai_generated: true },
  { description: "Labour — installation", quantity: 4, unit_price: 65, unit: "hr", ai_generated: true },
];

test.describe.serial("T — AI metadata contract", () => {
  let tenant: Tenant;

  test.beforeAll(async () => {
    tenant = await createTestTenant("ai-meta");
  });

  test("G34: AI-drafted line items use catalogue units — never unit=job", async () => {
    const contact = await seedContact(tenant, { name: "E2E AI Customer" });
    const quote = await api(tenant, "/quotes", {
      method: "POST",
      body: {
        contact_id: contact.id,
        title: "E2E AI cable run",
        line_items: AI_LINES,
      },
    });

    expect(quote.ai_generated).toBe(true);
    const units = (quote.line_items as Array<{ unit: string }>).map((li) => li.unit);
    for (const unit of units) {
      expect(CATALOGUE_UNITS).toContain(unit);
      expect(unit).not.toBe("job");
    }

    // The contract survives a round-trip read.
    const reread = (await api(tenant, "/quotes")) as Array<{
      id: string;
      ai_generated: boolean;
      line_items: Array<{ unit: string }>;
    }>;
    const stored = reread.find((q) => q.id === quote.id);
    expect(stored?.ai_generated).toBe(true);
    for (const li of stored?.line_items ?? []) {
      expect(li.unit).not.toBe("job");
    }
  });

  test("G34: a generated quote exposes the AI metadata contract", async () => {
    const contact = await seedContact(tenant, { name: "E2E AI Generate Customer" });
    const res = await apiRaw(tenant, "/quotes/generate", {
      method: "POST",
      body: {
        contact_id: contact.id,
        description:
          "Replace a consumer unit and install four new double sockets in a 3-bed semi in Stockport",
      },
    });
    if (res.status === 503) {
      // No LLM configured on the target api (local dev) — the metadata fields
      // only exist after a real generation pass, so nothing to assert.
      test.skip(true, "LLM not configured on target api (POST /quotes/generate -> 503)");
    }
    expect(res.status).toBe(201);

    const quote = res.json as {
      ai_generated: boolean;
      ai_confidence: number | null;
      ai_warnings: string[] | null;
      ai_assumptions: string[] | null;
      retrieval_status: string | null;
      line_items: Array<{ unit: string }>;
    };
    expect(quote.ai_generated).toBe(true);
    expect(quote.ai_confidence).not.toBeNull();
    expect(quote.ai_confidence).toBeGreaterThanOrEqual(0);
    expect(quote.ai_confidence).toBeLessThanOrEqual(1);
    expect(Array.isArray(quote.ai_warnings)).toBe(true);
    expect(Array.isArray(quote.ai_assumptions)).toBe(true);
    expect(["grounded", "weak_match", "no_index"]).toContain(quote.retrieval_status);
    for (const li of quote.line_items) {
      expect(CATALOGUE_UNITS).toContain(li.unit);
      expect(li.unit).not.toBe("job");
    }
  });
});
