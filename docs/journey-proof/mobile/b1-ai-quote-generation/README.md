# B1 — AI quote generation (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** fully UI-driven (Appium) — text typed into the intake form, generation submitted in-app. Resulting quote: `c0f27185-f767-48ef-b973-4ec57a1a0eca`.

Job description used: *"Consumer unit replacement, 3-bed semi in Derby, 10 circuits, RCBOs, SPD"*

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open `/(trade)/quote-intake` | Intake form: customer picker, job description, optional property details | "Quote intake" with Customer search, Job description (voice mic), optional fields — [01-quote-intake-empty.png](01-quote-intake-empty.png) | PASS |
| 2 | Enter description | Text accepted | Description entered; "Generate AI quote" CTA visible — [02-intake-description-entered.png](02-intake-description-entered.png) | PASS |
| 3 | Submit | Async generation (202), app returns to Quotes with progress banner | "Quote is generating — You'll be notified when it's ready for review." banner on Quotes — [03-generating-banner.png](03-generating-banner.png) | PASS |
| 4 | Poll until ready (~60s) | Banner flips to ready | "Your AI quote is ready — Tap to review and send it"; new draft appears at top of list — [04-quote-ready-banner.png](04-quote-ready-banner.png) | PASS |
| 5 | Open draft | Line items + AI metadata | Draft shows title, "AI confidence 40%", "AI assumptions & notes (6)", 5 guide-priced lines, total £729.16 — [05-ai-draft.png](05-ai-draft.png) | PASS |
| 6 | Expand assumptions | Assumptions + guide note | 5 assumptions (earthing/bonding, circuits sound, surface-mount, single visit, supply tails) + "Guide quote only…" note — [06-ai-assumptions-notes.png](06-ai-assumptions-notes.png) | PASS |

**API cross-check** ([api-quote-generated.json](api-quote-generated.json)): `ai_generated: true`, `ai_confidence: 0.4`, `retrieval_status: "grounded"`, `ai_warnings: []`, 5 `ai_assumptions`, `estimated_hours: 6.5`, 5 line items (CU unit, 10× RCBO, sundries, 5h install labour @ £55, 1.5h testing/certification). `retrieval_status` is **not rendered in the app UI** — verified via API only.

**Notes:**
- VAT shows 0% — correct for this tenant: `tenant.vat_registered` is falsy, so `tenant_vat_rate()` returns 0 (`services/api/app/calculations.py`). Not a defect.
- The generated quote was linked to a placeholder contact "Generated lead" (no email); B3 required assigning a real contact email (see [b3](../b3-send-quote/)).
