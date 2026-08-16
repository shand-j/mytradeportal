# React Native Technology Stack Report
## A Modern iOS App for Electricians to Run Their Business — and Reclaim Their Time

*Research date: August 2026. All library choices assume the React Native New Architecture era (Expo SDK 55+, RN 0.81+, React 19).*

---

## 1. Recommended Core Stack (Summary Table)

| Category | Recommended Pick | Runner-up |
|---|---|---|
| Framework | **Expo SDK 55+** (managed, dev builds, EAS Build/Update) | Bare RN (only for exotic native modules) |
| Navigation | **Expo Router v6** (file-based, deep links, iOS 26 Liquid Glass tabs) | React Navigation (custom transitions) |
| UI components | **NativeWind + React Native Reusables** (shadcn-style, Tailwind DX) | Tamagui (performance) / gluestack v3 |
| Animation & graphics | **Reanimated v4, Gesture Handler, Skia, FlashList, expo-image** | — (non-negotiable core) |
| Client state | **Zustand** | Redux Toolkit (if team-standardized) |
| Server state | **TanStack Query v5** | — |
| Local storage | **react-native-mmkv** + `expo-secure-store` (secrets) | AsyncStorage (avoid for anything sensitive) |
| Offline-first sync | **PowerSync + Supabase** | WatermelonDB (hand-rolled sync, high cost) |
| Auth | **Clerk (`@clerk/expo`)** or Supabase Auth | — |
| Biometrics | **expo-local-authentication** (Face ID / Touch ID gate on session) | — |
| Charts / P&L | **victory-native XL** (Skia-powered, 60–120fps) | react-native-gifted-charts |
| Calendar UI | **@howljs/react-native-calendar-kit** (week/day timeline, drag-drop) + **react-native-calendars** (month/agenda) | react-native-big-calendar |
| Native calendar sync | **expo-calendar** (EventKit) | — |
| Maps / nav | **react-native-maps** + deep links (`maps://` etc.) | — |
| Notifications | **expo-notifications** + expo-background-task | Notifee (advanced) |
| PDF / documents | **expo-print** + **expo-sharing** (HTML→PDF, offline) | react-native-html-to-pdf (bare) |
| Signature capture | **react-native-signature-canvas** | — |
| Camera / scanning | **expo-camera** + VisionKit/ML Kit document scanner + ML Kit OCR | Scanbot SDK (paid) |
| Payments | **@stripe/stripe-react-native** (PaymentSheet) + **Stripe Terminal RN SDK** (Tap to Pay on iPhone) + GoCardless (direct debit) | Adyen/Square terminals |
| AI agent / chat | **Vercel AI SDK 5** (`@ai-sdk/react`, server-side tools) | Raw provider SDKs |
| Voice input | **whisper.rn** (on-device Whisper) or expo-speech-recognition | Deepgram/OpenAI Whisper API (cloud) |
| On-device AI (iOS 26+) | **expo-ai-kit / expo-local-llm** (Apple Foundation Models) | @callstack/ai |

> ⚠️ **Do not** choose Realm/Atlas Device Sync for offline — it was retired September 30, 2025, despite stale blog posts recommending it.

---

## 2. Feature-by-Feature Stack Mapping

### Login, Onboarding, Touch/Face ID
- **Clerk** (or Supabase Auth) for email/OAuth/magic-link/passkeys; `@clerk/expo-passkeys` for passkeys; `useLocalCredentials()` gives one-line Face ID re-login.
- **expo-local-authentication** gates an existing session with Face ID/Touch ID (handle hardware/enrollment/permission-denied edge cases).
- **expo-secure-store** (iOS Keychain) for tokens; **expo-app-integrity** (App Attest) for hardening a business app.
- Onboarding: a multi-step NativeWind wizard persisting progress in MMKV; defer permissions (notifications, calendar, Face ID) until the feature that needs them ("ask in context" = fewest-clicks principle).

### Dashboard & Revenue Analytics / P&L
- **victory-native XL** (Skia) for revenue/profit trend lines, job-mix donut, cash-flow bars — gesture tooltips, smooth on ProMotion displays.
- P&L computed server-side (Supabase RPC/views) from invoices, payments, expenses, and materials; TanStack Query caches with stale-while-revalidate.
- An **"Admin time saved this week"** card — measurable time-reclamation metric — as a first-class dashboard widget (see §5, market positioning).

### Job Quoting, Quote Editing & Invoicing
- Quote and invoice are **one record with a status field** (draft → sent → approved → invoiced → paid) to avoid duplication and enable one-tap conversion.
- **expo-print** HTML templates render branded PDFs fully offline; tenant logo embedded as base64 so it renders in a basement with no signal; **expo-sharing** for the native share sheet.
- **react-native-signature-canvas** captures customer sign-off; store signature PNG + timestamp + signer name for the audit trail.
- **Tap to Pay on iPhone** via Stripe Terminal RN SDK (apply early for Apple's proximity-reader entitlement); Stripe PaymentSheet for card/Apple Pay links; **GoCardless** mandates for staged payments, maintenance plans, and landlord EICR contracts.

### Accountancy Software Integrations
Pattern: the app owns customers/jobs/invoices; accounting tools receive one-way pushes of *approved* invoices + contacts, payments synced back. All OAuth tokens live server-side (Supabase Edge Functions), never on device; sync via a queue table with idempotency keys.

| Provider | Notes for build |
|---|---|
| **Xero** | OAuth2 + **PKCE** (required for mobile); 30-min access tokens, rotating refresh tokens stored atomically; granular scopes mandatory for new apps from March 2026 |
| **QuickBooks Online** | 1-hour tokens, rotating refresh; batch endpoints + webhooks; scope by `realmId` |
| **FreeAgent** (UK sole traders) | Simplest token lifecycle (long-lived refresh); minimal access levels speed app review |
| **Sage Accounting** | ~5-minute access tokens — needs an aggressive server-side refresh daemon |

Optional shortcut: unified APIs (Apideck/Merge/Knit) to ship all four via one schema, at the cost of less control over VAT/CIS edge cases. UK MTD compliance is achieved *through* these integrations — a strong sales point.

### Job Scheduling & Calendar Integrations
- **react-native-calendar-kit** for the dispatcher week/day timeline (FlashList + Reanimated + Gesture Handler; pinch-zoom, drag-and-drop editing).
- **react-native-calendars** for month/agenda pickers.
- **expo-calendar** for two-way sync with the device's Apple/Google calendars; **expo-linking** / Expo Router deep links for "click to nav" (`maps://`, Google Maps URL schemes) and booking links.
- Scheduling UX best practices: fixed status set (Dispatched → En Route → On Site → Delayed → Completed), unscheduled-job tray with drag-and-drop, conflict warnings, automated "your electrician is on the way" notifications, full-day offline cache.

### Customer Chat
- Recommended: **build on Supabase Realtime** (messages table + RLS + presence), with `react-native-gifted-chat` or FlyerHQ UI, push via expo-notifications. Zero per-MAU cost, tenant-scoped, chat joins naturally to jobs/customers.
- Faster-but-costlier alternatives: Stream Chat RN SDK (best DX, push is a paid add-on) or Sendbird UIKit (cheapest at high MAU).

### Customer CRM
- Data model: **Customer → Properties/sites → Jobs → Visits** (essential for landlords with many properties; EICRs are per-property). Communications as a unified timeline. Lifecycle segmentation (lead → quoted → active → maintenance contract).

### Tenant-by-Tenant Branding (My PT Hub–style)
- Design tokens (colors/typography/logo/cert template) resolved at runtime from a `tenants` table, cached in MMKV, refreshed on focus; branding propagates into PDF/cert HTML templates, emails, and the payment page. Never bundle tenant assets in the binary.
- Backend isolation via **Supabase Row-Level Security** (`tenant_id` on every table + membership policy) or **Clerk Organizations** (`orgId` in JWT as the tenant key — never trust client-sent tenant IDs).

### Customer + Business Users (two-sided)
- Role model in the same app (or a lightweight customer-facing build): business users see the full FSM; customers see a branded portal — quote approval, chat, certificate vault, service history, rebooking. Supabase RLS enforces the split.

### AI Integration
- **Voice-to-quote**: dictate site notes on-device (**whisper.rn**, Metal/Core ML accelerated) → cloud LLM with **structured output (Zod schemas)** extracts line items into a draft quote with live trade pricing. *"Quote in the client's inbox before you've parked."*
- **Agentic chat**: Vercel AI SDK 5 in RN against a server-side agent route with tool calling — the assistant can create quotes, look up jobs, check Zs values. Never ship API keys in the app.
- **Schedule optimization**: no credible off-the-shelf API; constraint scoring in your backend (skills/certs, Mapbox/Google Distance Matrix travel time, SLA, workload) with human override, plus an LLM that proposes reassignments with reasons.
- **On-device AI (iOS 26+)**: Apple Foundation Models via expo-ai-kit/expo-local-llm for private, offline tasks — summarising notes, smart replies, form autocomplete. Route on-device first, fall back to cloud.

### Electrical Certifications (UK/AU wedge)
- Model BS 7671 (18th Edition; watch Amendment 4 rollout) certificates as **structured, versioned form templates**: EIC, EICR (with C1/C2/C3 observation codes), Minor Works — schedules of circuits and test results (R1+R2, IR, polarity, Zs, RCD trip times).
- Built-in validation engine: max-Zs tables per protective device, pass/fail on test values, mandatory-field gating before sign-off.
- PDF output via expo-print mirroring the model-form layout; engineer + customer e-signatures; immutable audit trail; offline-first with sync queue. Templates ship as data so regulatory amendments don't require app releases.

---

## 3. Competitive Landscape (Why This Stack Wins)

The market is barbell-shaped:

- **Enterprise** (ServiceTitan ~$245–398/tech/mo + $5–50K implementation; simPRO — explicitly "look elsewhere under 10 techs"): too expensive, rigid, slow onboarding.
- **Generic SMB** (Jobber, Tradify, FieldPulse, Fergus): horizontal 50-trade tools. Recurring complaints: weak reporting, **no real offline** (FieldPulse *loses data* in basements), **"too many taps"** (FieldPulse), per-seat pricing, **forced vendor branding on your invoices** (Tradify).
- **Single-purpose UK cert apps**: iCertifi (market leader but **1.8★ on Trustpilot**, users actively fleeing), EasyCert (desktop-centric, dated).
- **Closest analogue**: Powered Now (UK, £15/mo, offline, built-in certs) — but weak quoting depth and no AI.

**Nobody combines** quoting + BS 7671 certification + invoicing + accounting sync + full white-label branding in one offline-first, mobile-first app.

## 4. Market Gaps Not Explicitly Called Out — Differentiation Opportunities

1. **Voice-first everything** — voice-to-quote *and* voice-to-certificate (auto-fill EICR fields from dictation + photo-based board capture). Attacks the #1 time sink directly.
2. **Unified compliance engine** — embedded BS 7671 calculators (cable sizing, volt drop, max Zs) at quote/cert time; NICEIC/NAPIT portal export; certs *inside* the job flow, not a separate app.
3. **"Fewest taps" + true offline as a brand promise** — local-first data (PowerSync), giant touch targets, glove-friendly; complete job → cert → invoice → payment in ≤5 screens. Name competitors' failures in marketing.
4. **Branded homeowner client app** — certificate vault, EICR-due reminders (UK rental EICRs are legally required every 5 years = compliance-driven recurring engagement), service history, one-tap rebook. A B2B2C retention loop no competitor owns.
5. **Job-volume or flat transparent pricing** (ServiceM8's model, published prices, no add-on maze) — e.g. ≤£15/mo solo tier undercutting Powered Now and iCertifi.
6. **AI regulations copilot** — plain-English BS 7671/NEC assistant; auto-flag cert errors before sign-off to reduce comebacks and scheme-assessment risk.
7. **Time-reclamation positioning** — a visible "evenings saved" metric; automate the evening admin stack end-to-end (quote follow-ups, payment chasing, review requests, EICR renewal reminders).
8. **Landlord/letting-agent multi-property accounts** — per-property cert-status dashboard; horizontal SMB tools structurally won't build this.

**Highest-conviction wedge:** UK solo electricians — an offline-first, voice-first, fully-branded quote+cert+invoice app at ≤£15/mo, targeting iCertifi's fleeing base; then AU (ServiceM8's iOS-only lock-in leaves Android unserved) and US (NEC variant).

## 5. Architecture Snapshot

```
RN app (Expo SDK 55+, Expo Router, NativeWind/Reusables, Reanimated)
  ├─ Zustand + TanStack Query + MMKV (local state/cache)
  ├─ PowerSync ←→ Supabase (Postgres + RLS multi-tenancy + Realtime chat + Storage)
  ├─ Supabase Edge Functions: OAuth token vault (Xero/QBO/FreeAgent/Sage),
  │   sync queues, AI agent route (Vercel AI SDK, tool calling), PDF/branding resolution
  ├─ Stripe Connect (per-tenant payouts) + Terminal (Tap to Pay) + GoCardless
  └─ expo-calendar / expo-notifications / expo-local-authentication / whisper.rn
```

## 6. Key Risks & Verification Notes

- Apple **proximity-reader entitlement** for Tap to Pay requires approval — apply early.
- Xero's granular-scope migration (March 2026) and token rotation: build the token vault first.
- Verify GoCardless billing-request details against current docs before build.
- NICEIC/NAPIT scheme submission goes through their portals — digital certs are accepted as PDFs, but don't claim "scheme submission" without verifying current policy.
- Stripe PaymentSheet works with Customer objects (not Accounts v2); plan Connect integration accordingly.
