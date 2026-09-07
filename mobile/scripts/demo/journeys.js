/**
 * Shared demo journey definitions for the interactive mock iOS app.
 *
 * Each journey is an ordered list of scenes. A scene has:
 *   - caption: on-screen marketing caption shown while the scene plays.
 *   - minMs:   minimum time the scene stays on screen (so narration/captions
 *              are readable even if the interaction itself is fast).
 *   - action:  async fn(page, h) that drives the UI for that scene.
 *
 * The same definitions are consumed by:
 *   - record-demo-video.js (records a video + live-timed captions)
 *   - capture-journey-screenshots.js (stills for storyboards)
 *
 * Navigation rule: never call page.goto() after the initial load. The app keeps
 * auth/business state in memory (Zustand); a reload would wipe the session. All
 * navigation must go through in-app controls.
 */

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function makeHelpers(baseUrl) {
  async function tap(page, testId, settleMs = 500) {
    // Prefer the visible instance: expo-router can keep previous screens in the
    // DOM (hidden), so a plain .first() may resolve a stale hidden element.
    const visible = page.locator(`[data-testid="${testId}"]:visible`).first();
    const any = page.locator(`[data-testid="${testId}"]`).first();
    const locator = (await visible.count()) > 0 ? visible : any;
    await locator.waitFor({ state: "visible", timeout: 15000 });
    await locator.click({ force: true });
    await sleep(settleMs);
  }

  async function tapText(page, text, settleMs = 500) {
    const locator = page.getByText(text, { exact: false }).first();
    await locator.waitFor({ state: "visible", timeout: 15000 });
    await locator.click({ force: true });
    await sleep(settleMs);
  }

  async function tapAnyText(page, regex, settleMs = 500) {
    const locator = page.getByText(regex).first();
    await locator.waitFor({ state: "visible", timeout: 15000 });
    await locator.click({ force: true });
    await sleep(settleMs);
  }

  async function fillInput(page, index, value) {
    const input = page.locator("input, textarea").nth(index);
    await input.waitFor({ state: "visible", timeout: 15000 });
    await input.fill(value);
    await sleep(150);
  }

  async function fillPlaceholder(page, placeholder, value) {
    const input = page.getByPlaceholder(placeholder, { exact: false }).first();
    await input.waitFor({ state: "visible", timeout: 15000 });
    await input.fill(value);
    await sleep(150);
  }

  async function typeCode(page, code) {
    const first = page.locator("input").first();
    await first.waitFor({ state: "visible", timeout: 15000 });
    await first.click();
    await sleep(150);
    await first.pressSequentially(code, { delay: 90 });
    await sleep(300);
  }

  async function waitText(page, text, timeout = 15000) {
    await page.getByText(text, { exact: false }).first().waitFor({ state: "visible", timeout });
  }

  async function firstBooking(page, settleMs = 500) {
    const locator = page.locator('[data-testid^="booking-"]').first();
    await locator.waitFor({ state: "visible", timeout: 15000 });
    await locator.click({ force: true });
    await sleep(settleMs);
  }

  return { baseUrl, sleep, tap, tapText, tapAnyText, fillInput, fillPlaceholder, typeCode, waitText, firstBooking };
}

/* ------------------------------------------------------------------ */
/* Electrician journey: log in, review an AI draft, approve, schedule. */
/* ------------------------------------------------------------------ */
const electricianJourney = {
  id: "electrician",
  title: "The Electrician's Journey",
  subtitle: "Run your whole business from your phone",
  scenes: [
    {
      caption: "One app, white-labelled for every electrician.",
      minMs: 3200,
      action: async (page, h) => {
        await page.goto(h.baseUrl, { waitUntil: "networkidle" });
        await h.waitText(page, "My Trade Portal");
        await h.sleep(800);
      },
    },
    {
      caption: "Electricians log in to their mobile back office.",
      minMs: 3600,
      action: async (page, h) => {
        await h.tap(page, "entry-trade-login");
        await h.waitText(page, "Electrician login");
        await h.sleep(600);
        await h.tapText(page, "Sign in");
        await h.waitText(page, "Top leads");
      },
    },
    {
      caption: "Every morning opens on the hottest leads and today's calendar.",
      minMs: 3800,
      action: async (page, h) => {
        await h.sleep(1200);
      },
    },
    {
      caption: "One tap opens the lead — customer, photos and notes.",
      minMs: 3600,
      action: async (page, h) => {
        await h.tapText(page, "Consumer unit upgrade");
        await h.waitText(page, "Lead detail");
        await h.sleep(900);
      },
    },
    {
      caption: "AI scopes the job from the customer's answers.",
      minMs: 3400,
      action: async (page, h) => {
        await h.tapText(page, "Generate AI quote");
        await h.waitText(page, "Quote intake");
        await h.sleep(700);
      },
    },
    {
      caption: "A few taps confirm the site details.",
      minMs: 3600,
      action: async (page, h) => {
        await h.tap(page, "intake-property-type-house");
        await h.tap(page, "intake-bedrooms-3");
        await h.tap(page, "intake-cu-location-hallway");
        await h.fillPlaceholder(page, "Driveway parking", "Driveway parking, key-safe 1234");
        await h.fillPlaceholder(page, "Any access restrictions", "Dog on site, side gate access");
        await h.sleep(700);
      },
    },
    {
      caption: "AI drafts the quote in seconds.",
      minMs: 3800,
      action: async (page, h) => {
        await h.tap(page, "intake-generate-quote", 800);
        await h.waitText(page, "Review AI quote");
        await h.sleep(1200);
      },
    },
    {
      caption: "Review the line items, VAT and total.",
      minMs: 3600,
      action: async (page, h) => {
        await h.sleep(1400);
      },
    },
    {
      caption: "Switch between time-and-materials and per-point pricing.",
      minMs: 4200,
      action: async (page, h) => {
        await h.tap(page, "pricing-per_point", 1200);
        await h.sleep(1000);
        await h.tap(page, "pricing-time_materials", 1000);
        await h.sleep(600);
      },
    },
    {
      caption: "AI drafts, humans approve — you always have the final say.",
      minMs: 3600,
      action: async (page, h) => {
        await h.tapAnyText(page, /Approve & send|Update quote|Save changes/, 900);
        await h.sleep(600);
      },
    },
    {
      caption: "The job lands on the calendar.",
      minMs: 3400,
      action: async (page, h) => {
        await h.tap(page, "tab-calendar", 800);
        await page
          .locator('[data-testid="calendar-day"]')
          .first()
          .waitFor({ state: "visible", timeout: 15000 });
        await h.sleep(1100);
      },
    },
    {
      caption: "Navigate, call and assign — all from your pocket.",
      minMs: 4200,
      action: async (page, h) => {
        await h.firstBooking(page, 900);
        await h.sleep(1600);
      },
    },
  ],
};

/* ------------------------------------------------------------------ */
/* Customer journey: find electrician, request quote, accept, book.   */
/* ------------------------------------------------------------------ */
const customerJourney = {
  id: "customer",
  title: "The Customer's Journey",
  subtitle: "Get a trusted quote in minutes",
  scenes: [
    {
      caption: "Homeowners find their electrician with a 6-digit code.",
      minMs: 3600,
      action: async (page, h) => {
        await page.goto(h.baseUrl, { waitUntil: "networkidle" });
        await h.waitText(page, "My Trade Portal");
        await h.sleep(600);
        await h.typeCode(page, "123456");
        await h.tap(page, "entry-find-business", 700);
      },
    },
    {
      caption: "The app becomes their electrician's branded portal.",
      minMs: 3600,
      action: async (page, h) => {
        await h.waitText(page, "Request a quote");
        await h.sleep(1200);
      },
    },
    {
      caption: "Request a quote in under three minutes.",
      minMs: 3200,
      action: async (page, h) => {
        await h.tap(page, "entry-request-quote", 700);
        await h.waitText(page, "check we cover your area");
        await h.sleep(700);
      },
    },
    {
      caption: "Confirm your postcode — we check the service area.",
      minMs: 3200,
      action: async (page, h) => {
        await h.tap(page, "quote-check-area", 700);
        await h.sleep(500);
      },
    },
    {
      caption: "Your contact details, prefilled and simple.",
      minMs: 3000,
      action: async (page, h) => {
        await h.tap(page, "quote-contact-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Property age is the master variable for an accurate quote.",
      minMs: 3600,
      action: async (page, h) => {
        await h.sleep(900);
        await h.tap(page, "quote-property-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Pick the job — the tiles match what this electrician offers.",
      minMs: 3400,
      action: async (page, h) => {
        await h.tap(page, "quote-category-consumer_unit", 500);
        await h.tap(page, "quote-category-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Answer a few structured questions.",
      minMs: 3200,
      action: async (page, h) => {
        await h.sleep(900);
        await h.tap(page, "quote-consumer-unit-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Add photos of the fuse board with a guided overlay.",
      minMs: 3200,
      action: async (page, h) => {
        await h.sleep(900);
        await h.tap(page, "quote-media-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "When do you need it? Emergencies route straight to a callback.",
      minMs: 3400,
      action: async (page, h) => {
        await h.sleep(900);
        await h.tap(page, "quote-urgency-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Optional budget context helps the electrician.",
      minMs: 3000,
      action: async (page, h) => {
        await h.tap(page, "quote-budget-continue", 700);
        await h.sleep(400);
      },
    },
    {
      caption: "Give consent and submit.",
      minMs: 3400,
      action: async (page, h) => {
        await h.tap(page, "quote-consent-terms", 300);
        await h.tap(page, "quote-consent-contact", 300);
        await h.tap(page, "quote-submit", 900);
        await h.sleep(600);
      },
    },
    {
      caption: "Honest expectations — the business reviews and sends the quote.",
      minMs: 3600,
      action: async (page, h) => {
        await h.waitText(page, "has your request");
        await h.sleep(1400);
        await h.tap(page, "quote-done", 900);
      },
    },
    {
      caption: "Track everything in your branded customer portal.",
      minMs: 3400,
      action: async (page, h) => {
        await h.waitText(page, "My quotes");
        await h.sleep(1200);
      },
    },
    {
      caption: "Open the quote — every line item and assumption is transparent.",
      minMs: 3800,
      action: async (page, h) => {
        await h.tap(page, "quote-card-q1", 800);
        await h.waitText(page, "Assumptions");
        await h.sleep(1200);
      },
    },
    {
      caption: "Accept the quote with one tap.",
      minMs: 3200,
      action: async (page, h) => {
        await h.tapText(page, "Accept quote");
        await h.waitText(page, "Book a date");
        await h.sleep(700);
      },
    },
    {
      caption: "Pick a day and time that suits you.",
      minMs: 3600,
      action: async (page, h) => {
        await h.tap(page, "book-day-1", 400);
        await h.tap(page, "book-time-1", 400);
        await h.sleep(700);
      },
    },
    {
      caption: "Confirm the booking — it's on both calendars instantly.",
      minMs: 4000,
      action: async (page, h) => {
        await h.tapText(page, "Confirm booking");
        await h.sleep(1800);
      },
    },
  ],
};

const journeys = {
  electrician: electricianJourney,
  customer: customerJourney,
};

module.exports = { journeys, makeHelpers, sleep };
