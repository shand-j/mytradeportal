/**
 * MARKETING — clip 01 standalone retake (AI quote drafting).
 *
 * Retake with a fresh fictional customer so the review screen shows the
 * corrected VAT math (the original batch-1 take predated the demo-data
 * VAT fix and showed 2000% VAT totals).
 *
 *   E2E_TENANT_SLUG=hartley-electrical \
 *   E2E_TRADE_EMAIL=tom@hartleyelectrical.example.com E2E_TRADE_PASSWORD='Sparky2026!' \
 *   pnpm exec wdio run wdio.sim.conf.ts --spec specs/94-marketing-ai-draft.spec.ts
 */
import { loginAsTrade } from "../helpers/auth";
import { handlePermissionAlert, waitForText } from "../helpers/ui";
import { abortClip } from "../demo/recorder";
import { recordClip01AiQuoteDrafting } from "../demo/clips";

const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";

const GRAHAM_DESCRIPTION =
  "Install an outdoor socket and a security light at the rear of a detached " +
  "house in Harrogate. Run about 15 metres of armoured cable from the kitchen " +
  "consumer unit, fit a new RCBO, and include all testing and certification.";

// Each retake must use a fresh customer — a completed run leaves the draft
// behind, and a rerun would create a duplicate quote for the same person.
const CUSTOMER_NAME = process.env.MKT_CUSTOMER_NAME ?? "Graham Porter";
const DESCRIPTION = process.env.MKT_DESCRIPTION ?? GRAHAM_DESCRIPTION;

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M1c: marketing clip 01 — AI quote drafting (retake)", () => {
  before(function () {
    this.timeout(0);
  });

  it("01-ai-quote-drafting", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);
    await handlePermissionAlert("allow");
    await recordClip01AiQuoteDrafting(CUSTOMER_NAME, DESCRIPTION);
  });
});
