/**
 * Demo test — Kimi acts as a "clueless homeowner" customer.
 *
 * NOT part of standard regression. Run explicitly:
 *   cd mobile && pnpm exec playwright test --config=playwright.config.demo.ts
 *
 * Flow:
 *   1. Seed a sparse lead so the AI chat has a lot to ask about.
 *   2. Seed a customer login for that lead + kick off the first AI followup.
 *   3. Log in as the customer, open the chat.
 *   4. Loop: read the latest AI message → hand it to Kimi with a customer
 *      persona → post Kimi's reply back into the chat → wait for the next AI
 *      message. Break when the AI closes the conversation.
 *   5. Wait for the backend to re-quote in the background, then assert the
 *      resulting quote's ``ai_confidence`` meets the threshold.
 *
 * Requires ``LLM_API_KEY`` (and optionally ``LLM_API_BASE`` /
 * ``LLM_MODEL``) in the environment — the same variables the backend uses.
 */

import { test } from "@playwright/test";
import {
  api,
  createTestTenant,
  expect,
  fill,
  loginAsCustomer,
  seedCommunication,
  seedCustomer,
  seedLead,
  sleep,
  tap,
  Tenant,
} from "./helpers";
import { generateCustomerReply, PERSONA } from "./customer-persona";

const CUSTOMER_PASSWORD = "Demo-Customer-1!";
// The demo proves the AI chat drives confidence UP meaningfully — assert on
// the lift from the initial auto-draft (which is priced from the sparse lead
// alone) to the post-triage re-quote. Confidence 2.0 formula is
// 0.3 + 0.3*grounded_ratio + 0.4*completeness. A rich chat can push
// completeness by ~0.4-0.7 → ~0.16-0.28 confidence lift even without any
// catalogue grounding. 0.15 is a comfortable floor that would fail if the
// chat contributed nothing.
const CONFIDENCE_LIFT_THRESHOLD = 0.15;
const MAX_CUSTOMER_TURNS = 6;
// Match the two real backend closure messages from
// ``services/api/app/routers/communications.py`` — the confident closure
// contains "notified once" and the callback closure contains "give you a
// call". Everything else (including "Thanks for letting us know…"
// acknowledgements at the start of a question) is a live turn.
const CLOSURE_PATTERN = /notified once|give you a call/i;

test.describe("@demo Kimi-driven customer chat", () => {
  let tenant: Tenant;
  let leadId: string;
  let customerEmail: string;

  test.beforeAll(async () => {
    test.setTimeout(600_000);
    if (!process.env.LLM_API_KEY && !process.env.OPENAI_API_KEY) {
      test.skip(
        true,
        "LLM_API_KEY (or OPENAI_API_KEY) is required for the Kimi-driven customer persona"
      );
    }
    tenant = await createTestTenant("demo-chat");
    customerEmail = "demo-customer@e2e.example.com";

    // Sparse structured_data on purpose — this gives the AI real gaps to ask
    // about, so the triage produces a meaningful completeness lift.
    const lead = await seedLead(tenant, {
      title: PERSONA.leadTitle,
      category: PERSONA.category,
      contact: {
        name: "Demo Customer",
        email: customerEmail,
        phone: "07700 900700",
        postcode: PERSONA.postcode,
      },
      urgency: "this_week",
      structuredData: {
        notes: PERSONA.leadRawText,
      },
    });
    leadId = lead.id;
    await seedCustomer(tenant, {
      email: customerEmail,
      password: CUSTOMER_PASSWORD,
      fullName: "Demo Customer",
      phone: "07700 900700",
      quoteRequestId: leadId,
    });
    // Kick off the first AI followup so the chat opens with a live question.
    await seedCommunication(tenant, { quoteRequestId: leadId, turns: 1 });
  });

  test.slow();
  test("@demo Kimi-as-customer drives quote confidence above threshold", async ({ page }) => {
    await loginAsCustomer(page, tenant, {
      email: customerEmail,
      password: CUSTOMER_PASSWORD,
    });
    await tap(page, "customer-ai-banner");
    await page
      .locator('[data-testid="chat-composer"]')
      .waitFor({ state: "visible", timeout: 30_000 });

    const askedByAi: string[] = [];
    const answered: string[] = [];
    let closed = false;

    for (let turn = 0; turn < MAX_CUSTOMER_TURNS; turn++) {
      const aiMessage = await readLatestAgentMessage(page);
      askedByAi.push(aiMessage);
      console.log(`[demo] turn ${turn + 1} — AI asked: ${aiMessage}`);

      if (CLOSURE_PATTERN.test(aiMessage)) {
        closed = true;
        break;
      }

      const reply = await generateCustomerReply({
        askedSoFar: askedByAi,
        answeredSoFar: answered,
        latestQuestion: aiMessage,
      });
      answered.push(reply);
      console.log(`[demo] turn ${turn + 1} — customer replied: ${reply}`);

      const previousAgentCount = await countAgentMessages(page);
      await fill(page, "chat-composer", reply);
      await tap(page, "chat-send");
      await waitForAgentMessageIncrease(page, previousAgentCount, 200_000);
      await sleep(1000);
    }

    expect(closed, `Chat did not close within ${MAX_CUSTOMER_TURNS} customer turns`).toBe(true);

    // Sample the initial auto-draft quote (created on lead submission with a
    // sparse description, so its confidence is low) so we can distinguish it
    // from the post-triage re-quote below.
    const initial = await waitForQuoteFromRequest(tenant, leadId, 60_000);
    console.log(
      `[demo] initial quote ${initial.reference ?? initial.id} — ` +
        `ai_confidence=${initial.ai_confidence}, total=${initial.total}, ` +
        `retrieval_status=${initial.retrieval_status ?? "?"}`
    );

    // Log what the AI chat actually persisted so a failed threshold is easy to
    // diagnose (empty ai_extracted vs. rich extraction).
    try {
      const request = (await api(tenant, `/quote-requests/${leadId}`)) as {
        structured_data?: { ai_extracted?: Record<string, unknown> };
      };
      const extracted = request.structured_data?.ai_extracted ?? {};
      console.log(
        `[demo] extracted keys after chat: ${JSON.stringify(Object.keys(extracted))}`
      );
      console.log(`[demo] extracted facts: ${JSON.stringify(extracted)}`);
    } catch (err) {
      console.log(`[demo] could not fetch quote_request diagnostics: ${(err as Error).message}`);
    }

    // The chat closure triggers requote_after_triage_close as a background
    // task. That task runs a full Kimi generate call (60-120s), then
    // overwrites the draft with completeness set from the enriched intake.
    // Poll for the confidence to CHANGE from the auto-draft baseline.
    const quote = await waitForConfidenceUpdate(
      tenant,
      leadId,
      Number(initial.ai_confidence ?? 0),
      240_000
    );
    const confidence = Number(quote.ai_confidence ?? 0);
    const initialConfidence = Number(initial.ai_confidence ?? 0);
    const lift = Number((confidence - initialConfidence).toFixed(2));
    console.log(
      `[demo] requoted ${quote.reference ?? quote.id} — ai_confidence=${confidence}, ` +
        `total=${quote.total}, retrieval_status=${quote.retrieval_status ?? "?"}`
    );
    console.log(
      `[demo] CONFIDENCE LIFT: ${initialConfidence} → ${confidence} (+${lift}) ` +
        `(threshold ≥ ${CONFIDENCE_LIFT_THRESHOLD})`
    );

    expect(
      lift,
      `AI chat lift ${lift} below threshold ${CONFIDENCE_LIFT_THRESHOLD} — ` +
        `chat extraction did not meaningfully raise quote confidence`
    ).toBeGreaterThanOrEqual(CONFIDENCE_LIFT_THRESHOLD);
  });
});

async function readLatestAgentMessage(page: import("@playwright/test").Page): Promise<string> {
  const locator = page.locator('[data-testid="chat-message-agent"]');
  await locator.first().waitFor({ state: "visible", timeout: 60_000 });
  const count = await locator.count();
  const raw = await locator.nth(count - 1).innerText();
  // The agent bubble renders as: assistantName \n message body \n timestamp.
  // Timestamps look like "12:34 PM"; assistant name is a short label. Take
  // the longest non-timestamp line as the body.
  const lines = raw
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !/^\d{1,2}:\d{2}\s?(AM|PM)?$/i.test(l));
  if (lines.length === 0) return raw.trim();
  return lines.reduce((longest, line) => (line.length > longest.length ? line : longest));
}

async function countAgentMessages(page: import("@playwright/test").Page): Promise<number> {
  return page.locator('[data-testid="chat-message-agent"]').count();
}

async function waitForAgentMessageIncrease(
  page: import("@playwright/test").Page,
  previousCount: number,
  timeoutMs: number
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if ((await countAgentMessages(page)) > previousCount) return;
    await sleep(1500);
  }
  throw new Error(
    `No new AI message appeared within ${timeoutMs}ms (still ${previousCount} agent messages)`
  );
}

async function waitForQuoteFromRequest(
  tenant: Tenant,
  quoteRequestId: string,
  timeoutMs: number
): Promise<{
  id: string;
  reference?: string;
  ai_confidence?: number | null;
  ai_generated?: boolean;
  total?: string;
  retrieval_status?: string | null;
}> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const rows = (await api(tenant, "/quotes")) as Array<{
      id: string;
      reference?: string;
      quote_request_id: string | null;
      ai_confidence?: number | null;
      ai_generated?: boolean;
      total?: string;
      retrieval_status?: string | null;
    }>;
    const match = rows.find(
      (q) => q.quote_request_id === quoteRequestId && q.ai_generated === true
    );
    if (match && match.ai_confidence != null) return match;
    await sleep(2500);
  }
  throw new Error(
    `No AI-generated quote for request ${quoteRequestId} appeared within ${timeoutMs}ms`
  );
}

async function waitForConfidenceUpdate(
  tenant: Tenant,
  quoteRequestId: string,
  baseline: number,
  timeoutMs: number
): Promise<{
  id: string;
  reference?: string;
  ai_confidence?: number | null;
  total?: string;
  retrieval_status?: string | null;
}> {
  const deadline = Date.now() + timeoutMs;
  let lastSample: number | null = null;
  while (Date.now() < deadline) {
    const rows = (await api(tenant, "/quotes")) as Array<{
      id: string;
      reference?: string;
      quote_request_id: string | null;
      ai_confidence?: number | null;
      ai_generated?: boolean;
      total?: string;
      retrieval_status?: string | null;
    }>;
    const match = rows.find(
      (q) => q.quote_request_id === quoteRequestId && q.ai_generated === true
    );
    const current = Number(match?.ai_confidence ?? 0);
    if (match && current !== baseline && current !== lastSample) {
      console.log(`[demo] requote sample: confidence changed ${baseline} → ${current}`);
      return match;
    }
    lastSample = current;
    await sleep(5000);
  }
  throw new Error(
    `Confidence did not change from baseline ${baseline} within ${timeoutMs}ms ` +
      `(requote_after_triage_close likely still running or failed)`
  );
}
