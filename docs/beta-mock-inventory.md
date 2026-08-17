# Beta Mock & Placeholder Inventory

> A curated audit of every mock, scripted fake, placeholder handler, and demo literal currently in the codebase, each mapped to a headline change requirement for Beta. Generated 2026-08-17 against branch `mvp-pivot`.
>
> **Legend:** 🔴 headline differentiator faked · 🟠 core flow mock-bound · 🟡 scaffolding/cosmetic · ⚪ backend stub.

## How to read this

The app runs in two modes: **connected** (`config.apiEnabled`, i.e. `EXPO_PUBLIC_API_BASE_URL` set) and **demo** (mock data). Many screens already fall back to real APIs when connected, but a significant surface is still mock-only or scripted even in connected mode. This document tracks what must become real for Beta.

**The three Beta blockers this list rolls up to:**

1. **Make the AI real** — voice transcription, voice-to-quote, voice-to-cert, RAG quote generation, customer AI assistant, dashboard insights (§A).
2. **Make offline real** — persistent queue + backend replay on reconnect (§A7).
3. **Cut the mock fallbacks** — so connected mode is fully backend-bound (§B, §C, §G).

Voice and offline are the marketed differentiators and are currently **100% simulated**.

---

## A. Headline differentiators that are currently faked (highest priority)

| # | Sev | Mock / placeholder (location) | Beta change requirement |
|---|---|---|---|
| A1 | 🔴 | **Voice transcription** — `src/components/VoiceCaptureSheet.tsx` streams a hardcoded string word-by-word (`setTimeout`); no mic, no audio capture, no STT | Real on-device/cloud transcription (e.g. Whisper) capturing actual speech |
| A2 | 🔴 | **Voice-to-quote** — `src/screens/trade/VoiceQuoteScreen.tsx` `DICTATION` + `EXTRACTED` line items hardcoded; no LLM; writes to `MOCK_QUOTES` | Real transcript → structured LLM extraction (Zod-typed) → draft quote persisted via API |
| A3 | 🔴 | **Voice-to-cert** — `src/screens/trade/CertificateScreen.tsx` `DICTATION` + `VOICE_OBSERVATIONS` hardcoded; writes to `MOCK_CERTIFICATES` | Real dictation → EICR field extraction with BS 7671 validation |
| A4 | 🔴 | **RAG quote generation** — real path `POST /quotes/generate` exists but returns **HTTP 503** ("No priced line items"): the 8,464-item catalogue has **0 labour/service items** so the LLM correctly refuses | Add a labour/service cost layer (day/hour/per-circuit rates) so a real GPT-priced quote is produced end-to-end |
| A5 | 🔴 | **Customer AI assistant** — `src/screens/customer/MessagesScreen.tsx` `FOLLOW_UP` is a scripted Q&A with fake "typing…" delays; no LLM, no persistence | Real LLM-driven clarifying questions wired to the quote request record |
| A6 | 🟠 | **Dashboard "AI insight"** — `src/screens/trade/DashboardScreen.tsx` sparkles banner just links to the newest lead; no analysis | Real AI insight (revenue / scheduling / follow-up recommendation) |
| A7 | 🔴 | **Offline-first sync** — `src/stores/offlineStore.ts` uses `setTimeout` to fake upload; in-memory queue (lost on reload); manual online toggle | Real persistent queue (MMKV/PowerSync) + backend replay on reconnect |

---

## B. Customer portal (mock-bound)

| # | Sev | Mock / placeholder | Beta change requirement |
|---|---|---|---|
| B1 | 🟠 | Received-quote lifecycle — `src/screens/customer/RequestsScreen.tsx` reads `MOCK_QUOTES`; real backend requests render as read-only cards (not tappable) | Wire real quote detail → accept → reject → book against the backend |
| B2 | 🟠 | Customer calendar — `src/screens/customer/CustomerCalendarScreen.tsx` reads `MOCK_JOBS` | Load the logged-in customer's real appointments |
| B3 | 🟠 | Customer profile — `src/screens/customer/ProfileScreen.tsx` reads `MOCK_CUSTOMERS[0]`; save is local-only | Load/persist real customer profile + preferences |
| B4 | 🟠 | Messages have no backend/persistence (see A5) | Real chat persistence (messages table + realtime) |
| B5 | 🟡 | "Change password" `onPress={() => {}}` (`ProfileScreen.tsx:171`) | Real password change |
| B6 | 🟡 | "Request a revised quote" ×2 `onPress={() => {}}` (`RequestsScreen.tsx:369,393`) | Wire to re-quote / message flow |
| B7 | 🟡 | "Forgot password?" `onPress={() => {}}` (`LoginScreen.tsx:111`) | Real password reset |
| B8 | 🟠 | Registration missing **address + preferred contact** (`LoginScreen.tsx`) | Add fields; persist to customer record |

---

## C. Trade portal (mock or partial)

| # | Sev | Mock / placeholder | Beta change requirement |
|---|---|---|---|
| C1 | 🟠 | CRM — `src/screens/trade/CRMScreen.tsx` fully mock (customers/quotes/jobs/invoices matched by name) | Wire to `/contacts` + related real data |
| C2 | 🟠 | Certificates list + detail — `src/screens/trade/CertificatesScreen.tsx`, `app/(trade)/certificate/[id].tsx` 100% `MOCK_CERTIFICATES` | Real certificates API + storage |
| C3 | 🟠 | Analytics P&L — `src/screens/trade/AnalyticsScreen.tsx` cost/quoted breakdown from `MOCK_JOBS`/`MOCK_QUOTES` even when connected | Real cost/margin analytics from backend |
| C4 | 🟠 | Dashboard "pending quotes" value from `MOCK_QUOTES` (`DashboardScreen.tsx:79`) | Real pending-quotes KPI |
| C5 | 🟠 | Detail routes (`quote/job/invoice/lead/[id]`) fall back to MOCK when a real record isn't found | Remove mock fallback for Beta; handle not-found properly |
| C6 | 🟡 | "Add note" / "Edit details" `onPress={() => {}}` (`CRMScreen.tsx:145,146`) | Real note + edit persistence |
| C7 | 🟡 | "Share QR code" ×2 `onPress={() => {}}` (`LeadsScreen.tsx:151`, `QuotesScreen.tsx:169`) | Real business QR / deep-link share |

---

## D. Onboarding & auth (demo scaffolding)

| # | Sev | Mock / placeholder | Beta change requirement |
|---|---|---|---|
| D1 | 🟠 | `src/screens/onboarding/steps/PlanPaymentStep.tsx` DEMO_MODE simulates Paddle checkout via `setTimeout` | Real Paddle checkout + webhook confirmation |
| D2 | 🟡 | Prefilled `owner@demo.trade` / `demo12345678` (`AccountStep.tsx`, `WelcomeScreen.tsx`) | Remove prefilled creds for Beta |
| D3 | 🟡 | Prefilled Companies House `12345678` (`BusinessIdentityStep.tsx:26`) | Real CH lookup/validation |
| D4 | 🟠 | `AddressServiceAreaStep.tsx` uses `MOCK_ADDRESSES` — real `address_lookup` router exists but is unused | Wire the real address lookup |
| D5 | 🟡 | `EntryPostcodeStep.tsx:71` "Sign in" `onPress` is a mock placeholder | Wire customer sign-in from capture flow |
| D6 | 🟡 | `LoginScreen.tsx` prefilled demo creds + visible "Demo: … / demo123" hint (`:128`) | Remove demo hint/prefill for Beta |
| D7 | 🟡 | `EntryScreen.tsx` error text "Try '123456' or '654321'" (`:29`); hardcoded `demo-customer` on quote complete (`:40`) | Real business-code validation; real customer identity |

---

## E. Placeholder literals shown to users

| # | Sev | Mock / placeholder | Beta change requirement |
|---|---|---|---|
| E1 | 🟠 | Invoice bank details hardcoded "Sort code 20-00-00 · Acc 12345678" (`InvoiceDetailScreen.tsx:124`) | Pull real tenant bank/payment details |
| E2 | 🟡 | Business landing shows name only — **logo image not rendered** (`EntryScreen.tsx`) | Render real tenant logo (white-label) |
| E3 | 🟡 | Demo quote validity is **6 days** (PRD says 30) (`mockQuotes.ts:19`) | Real validity from quote record |
| E4 | 🟡 | Onboarding "Coming soon in dashboard" (`TeamCapacityStep.tsx:23`) | Implement or remove team-capacity view |

---

## F. Backend stubs

| # | Sev | Stub | Beta change requirement |
|---|---|---|---|
| F1 | ⚪ | `services/api/app/routers/quotes.py` — `/generate-boq` + BoQ read endpoints return **501** | Decide: enable OCERP or remove from Beta surface |
| F2 | ⚪ | `services/ocerp/ocerp/routers/takeoff.py` — pdf/cad/photo return **501** | Out of Beta scope; keep parked |
| F3 | ⚪ | No routers for voice/transcribe or AI insights | Add endpoints backing A1–A3, A6 |
| F4 | ⚪ | `reviews.py` / `communications.py` routers exist but are **not wired to mobile** | Wire or defer explicitly |

---

## G. Mock data files (the sources feeding §B and §C)

Location: `services/pwa/src/data/`

`mockBusinesses.ts` · `mockCertificates.ts` · `mockCustomers.ts` · `mockInvoices.ts` · `mockJobs.ts` · `mockLeads.ts` · `mockMedia.ts` · `mockQuotes.ts`

**Beta requirement:** each becomes a real API-backed source; retain only as test fixtures behind `!config.apiEnabled`.

---

## Suggested burn-down order

1. **A4** (real RAG quote works) — unblocks the whole trade quoting story; closest to done.
2. **A1–A3** (real voice) — the headline differentiator.
3. **A7** (real offline) — the second headline differentiator.
4. **B1–B3** (customer portal real data) — needed for a coherent customer Beta.
5. **C1–C5** (trade portal real data) + **G** (retire mocks behind fixtures).
6. **D1, D4, E1** (payments, address, bank details) — real money/identity paths.
7. **A5, A6, B4** (AI assistant + insights + chat persistence) — polish differentiators.
8. **Cosmetic cleanup** (D2, D3, D5–D7, E2–E4, B5–B7, C6–C7) — remove demo scaffolding before public Beta.
