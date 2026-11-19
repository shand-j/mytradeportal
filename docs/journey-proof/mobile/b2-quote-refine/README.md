# B2 — Quote review / edit / Refine with AI (mobile)

**Captured:** 2026-10-23 · same build/account as [a2](../a2-trade-login/)
**Driving:** fully UI-driven (Appium) on the B1 draft quote `c0f27185-f767-48ef-b973-4ec57a1a0eca`.

Refine instruction used: *"Add a note about notifying the DNO"*

| # | Step | Expected | Observed | Result |
|---|------|----------|----------|--------|
| 1 | Open draft quote (`/(trade)/quote/[id]`) | Review screen: header w/ AI confidence, assumptions, editable lines, Refine box | "Review quote" — all present (see [b1](../b1-ai-quote-generation/05-ai-draft.png)) | PASS |
| 2 | Type refine instruction | Instruction accepted in `refine-instructions` box | "Add a note about notifying the DNO" in the Refine with AI box — [01-refine-instruction-entered.png](01-refine-instruction-entered.png) | PASS |
| 3 | Tap "Refine quote" | Live LLM call, explicit busy state | "Refining…" disabled button + skeleton placeholders (the "RefineSkeleton" added post-#93) — [02-refining-skeleton.png](02-refining-skeleton.png) | PASS |
| 4 | Wait for result | Quote regenerated, manual edits preserved, summary shown | Returned in ~5 s. Line 1 replaced with catalogue-matched "Metal consumer unit 10-way with SPD surge protection and main switch" (£91.66 → £145.00); total £729.16 → £782.50 — [03-refined-totals.png](03-refined-totals.png) | PASS |
| 5 | Refine feedback card | "Refined by AI" summary + confidence + thumbs rating | "Updated consumer unit price to match catalogue and added note for DNO notification. AI confidence 60%. Was this refine helpful? 👍/👎" — [04-refined-by-ai-card.png](04-refined-by-ai-card.png) | PASS |

**API cross-check** ([api-quote-after-refine.json](api-quote-after-refine.json)): `ai_confidence: 0.6`, `ai_refine_summary: "Updated consumer unit price to match catalogue and added note for DNO notification."`, `ai_notes: "Please ensure to notify the DNO regarding the new consumer unit installation."` — the DNO instruction landed. The refine hang/no-op regression (#276) does **not** reproduce on this build.

**Note:** after refine, the "AI assumptions & notes" badge count dropped 6 → 1 (the refine replaced the notes block with the DNO note) — consistent behaviour.
