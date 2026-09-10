/**
 * MARKETING — clip 03 standalone retake (review & send).
 *
 * The backend's AI triage auto-drafts a quote from the customer's request,
 * so this clip opens the AI-drafted quote straight from the Quotes list,
 * reviews it, and sends it. Requires a draft quote from a "downlights"
 * request to exist (created by specs/90 clip 02, or any prior run).
 *
 *   E2E_TENANT_SLUG=hartley-electrical \
 *   E2E_TRADE_EMAIL=tom@hartleyelectrical.example.com E2E_TRADE_PASSWORD='Sparky2026!' \
 *   pnpm exec wdio run wdio.sim.conf.ts --spec specs/92-marketing-review-send.spec.ts
 */
import { loginAsTrade } from "../helpers/auth";
import { handlePermissionAlert, waitForText } from "../helpers/ui";
import { abortClip } from "../demo/recorder";
import { recordClip03ReviewAndSend } from "../demo/clips";

const TOM_EMAIL = "tom@hartleyelectrical.example.com";
const TOM_PASSWORD = "Sparky2026!";

afterEach(async function () {
  const state = (this as { currentTest?: { state?: string } }).currentTest?.state;
  if (state === "failed") await abortClip();
});

describe("M1b: marketing clip 03 — review and send", () => {
  before(function () {
    this.timeout(0);
  });

  it("03-review-and-send", async () => {
    await loginAsTrade(TOM_EMAIL, TOM_PASSWORD);
    await waitForText("Dashboard", 25000);
    await handlePermissionAlert("allow");
    await recordClip03ReviewAndSend();
  });
});
