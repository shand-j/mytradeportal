# Tradify Table-Stakes Parity Checklist

|  |  |
| --- | --- |
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · Governs scope of: [PRD-Customer-Portal.md](PRD-Customer-Portal.md), [PRD-Online-Payments.md](PRD-Online-Payments.md), [Delivery-Plan-Pre-Beta-to-Launch.md](Delivery-Plan-Pre-Beta-to-Launch.md) |
| **Source** | Tradify pricing/feature pages, checked September 2026 ([tradifyhq.com/pricing](https://www.tradifyhq.com/pricing)) |
| **Rule** | If we target Tradify users, anything on their **Lite** tier is table stakes. Gaps must be deliberate, documented, and survivable in a sales conversation. |

## Parity assessment

| Tradify capability (tier) | Our status | Phase | Notes |
| --- | --- | --- | --- |
| Job management, notes & tracking (Lite) | ✅ Exists | — | Core product |
| Scheduling + Google Calendar sync (Lite) | ✅/⚠️ Verify | — | Confirm sync depth matches |
| Quoting & invoicing (Lite) | ✅ Exists, AI-superior | — | Our differentiator |
| Pricing & markups (Lite) | ⚠️ Verify | — | Materials markup handling must match |
| **Online & credit card payments (Lite)** | ❌ **Was missing** | **Phase 0** | Now a beta blocker — [PRD-Online-Payments.md](PRD-Online-Payments.md) + Feature PRD F1 |
| Per-seat pricing (their model) | ✅ **Our attack line** | — | 5-person crew: Tradify Lite ≈£170/mo vs our Team £69 flat. Use in sales deck |
| **Data export / no lock-in** | ❌ **Was missing** | **Phase 0** | Feature PRD F3 — trust objection killer, marketing claimable |
| Email tracking (sent/viewed) (Lite) | ⚠️ Verify | Phase 1 | Quote/invoice viewed events also feed our funnel |
| Accounting sync — Xero/QuickBooks (Lite) | ✅ **Now all tiers** | Phase 1 (F5) | **Resolved:** Tradify Lite includes it, so ours is included from Sole Trader — parity, not a premium gate |
| AI features (SmartRead/SmartWrite — **Plus only, fair-usage throttle**) | ✅ **All our tiers, unmetered** | — | **Headline differentiator:** their AI is gated at ~£46/user with upgrade-forcing AUP; ours is everywhere with no counting |
| Quote/invoice reminders (Pro/Plus) | ✅ All tiers | Phase 0 (F2) | Ours exceeds theirs: AI-drafted copy, per-customer overrides |
| Progress invoicing (Pro) | 🔨 Pro tier | Phase 1 (F6) | Matches their gating — deposits at our Pro is acceptable parity |
| 14-day trial, all features | ✅ Matches | Phase 0 | Plus our engagement extension |
| Enquiry form & email inbox (Pro) | ✅/🔨 | Phase 1–2 | Our portal intake + widget exceeds this |
| Custom branding (Pro) | 🔨 | Phase 1–2 | Tradie-branded portal/QR covers customer-facing side; document branding verify |
| Customer comms history (Pro) | 🔨 | Phase 2 | Portal chat + notification log |
| Job photos & files (Pro) | 🔨 | Phase 1–2 | Intake photos exist; tradie-side attachments verify |
| Quote options & online acceptance (Pro) | 🔨/✅ | Phase 2 | Portal accept flow = online acceptance; multi-option quotes assess |
| Progress invoicing (Pro) | ❌ | Post-beta | Deposits land with payments P1; full progress invoicing later |
| Deposits / optional quote lines | 🔨 | Phase 1 | Feature PRDs F6/F7 |
| Timesheets, costing & bill tracking (Pro) | ❌ | Post-beta | Deliberate gap — log demand in beta |
| Mobile app (iOS/Android) | ✅/⚠️ | — | Tradie app is our strength; customer side deliberately web-first |
| Instant Website add-on ($12/mo) | ✅ Exceeded | Phase 1–2 | Our branded portal + widget is better and included |
| SmartRead/SmartWrite AI (Plus) | ✅/⚠️ | — | Our AI is broader and on every tier (unmetered) — headline differentiator |

## Standing rule for contributors

Before scoping any beta-phase feature, check this table: **does Tradify Lite already do it?** If yes and we don't, it's a parity gap — escalate to founder for phase placement rather than silently deferring. Update this table at each phase boundary; re-verify Tradify's page quarterly (they ship fast).