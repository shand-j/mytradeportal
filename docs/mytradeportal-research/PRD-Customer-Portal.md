# PRD — Customer-Facing Portal

| | |
|---|---|
| **Status** | Approved for planning |
| **Owner** | Founder (product) / Lead dev (delivery) |
| **Phase** | Beta-phase build — ship during beta once Observability (P0) lands; do not delay beta onboarding for it |
| **Pack** | [README-Document-Pack.md](README-Document-Pack.md) · [K3 Prompt](K3-Agent-Prompt-Observability-Layer-and-Pricing.md) · Depends on: [PRD-Observability-Layer.md](PRD-Observability-Layer.md) (attribution), [PRD-Pricing-and-Billing.md](PRD-Pricing-and-Billing.md) (tier gates, fair use) |

## 1. Problem Statement

PMF requires the tradie's *customers* to feel the product. Tradies want to hand a customer a QR code (van, business card, phone screen) or a 6-digit code and have that customer land somewhere useful. The critical constraint: **these customers are occasional users** — a homeowner needs a consumer unit replaced once a decade. Every step before first value (app store → install → register) loses a large share of them, and the tradie pays that cost in slower quote acceptance. The portal must be **web-first, app-optional**.

## 2. Goals & Non-Goals

**Goals**
- Zero-install path from QR/code to submitted quote request in under 2 minutes.
- Tradie-branded experience — the tradie's business is the hero; MyTradePortal is the plumbing.
- Self-serve portal: submit requests, view/accept quotes, view invoices, chat, and **pay invoices online** (see [PRD-Online-Payments.md](PRD-Online-Payments.md) — table stakes vs Tradify, beta blocker).
- Customer-side AI that fills the tradie's pipeline (intake briefs) without becoming a COGS or abuse liability.
- Free growth loop: every QR asset a tradie prints advertises the product.

**Non-goals**
- Mandatory app install anywhere in the customer journey.
- Open-ended customer chatbot (unbounded cost + hallucination liability on prices — rejected).
- Payments *infrastructure* beyond what the payments PRD specifies (no take-rate, no financing, no direct debit at beta).
- Customer accounts for prospects who haven't submitted anything (progressive registration only).

## 3. User Flows

### Flow A — New customer via QR / 6-digit code (primary)

1. Scan QR (van/card/phone screen) → lands directly on tradie-branded page `mytradeportal.co.uk/t/{org_slug}`. **Never routed through an app store.**
2. Quote-request form: name, phone/email, job description, photos, preferred timing. Unauthenticated but bot-protected.
3. **Progressive registration at submission:** verify phone/email via OTP or magic link → account created. No password, no profile wizard.
4. Portal home: request status timeline → quotes (view / accept / ask a question) → invoices (view / **pay securely now**) → chat.
5. Notifications (quote ready, invoice due, tradie replied) via SMS/email with **magic links deep-linking to the object**. For occasional users the notification *is* the interface.
6. PWA add-to-home-screen prompt from second visit; app-store path offered to repeat customers (landlords, property managers — the habitual segment).

### Flow B — 6-digit code

Same destination, typed. Covers verbal handover, printed invoices, voicemail.

### Flow C — Embeddable widget & shareable link

JS/iframe widget for the tradie's own website + shareable link for Google Business Profile, Facebook, Checkatrade. The tradie gets a branded intake form they could never build; we get distribution on their properties.

## 4. Requirements

### 4.1 Surfaces (P0 in beta)

- Vanity URL + tradie-branded landing page (name/logo/colours where available).
- QR generation per org + downloadable asset pack (van decal artwork, business-card PDF, invoice footer).
- 6-digit code resolution.
- Embeddable widget + shareable link.
- `entry_channel` tagged on every session/event: `qr_van | qr_card | code | widget | direct | app`.

### 4.2 Portal (P0 in beta)

- Unauthenticated quote-request form with **Cloudflare Turnstile + rate limits; no LLM call before contact verification.**
- Lightweight customer auth (phone/magic-link OTP) — separate from staff auth, strictly scoped to the customer's own data (object-level authorization tests mandatory).
- Portal home: status timeline, quotes, invoices, chat.
- Notification system: SMS/email + magic-link deep links.
- PWA manifest/service worker; install prompt logic.

### 4.3 Customer-side AI (P0 guardrails; features phased)

| Feature | Tier | Constraints |
|---|---|---|
| **Intake brief** (photos+description → structured job brief) | All tiers | Cheap bounded call, one per request, post-verification only. Kept generous — it is the tradie's pipeline and our acquisition engine |
| **Chat assistant** | **Pro gate** | Scoped retrieval over that customer's data + FAQs; small cheap model; hard turn caps; "your tradesperson will reply" handoff |
| Status/timeline summaries | All tiers | Trivial cost |
| Open-ended chatbot | — | **Do not build** |

- All customer AI events: `actor_type=customer`, attributed to the tradie's org, `entry_channel` set (Observability PRD schema).
- Abuse guardrails (Pricing PRD): burst limits, cheap-route fallback, staff alerts.

## 5. Metrics & Success Criteria

| Metric | Beta target |
|---|---|
| QR/code landing → form start | ≥60% |
| Form start → verified submission | ≥50% |
| Submission → tradie response | <24h median (tradie behaviour we measure, not enforce) |
| Quote viewed within 48h of notification | ≥70% |
| Repeat-visit PWA installs | Track only (baseline) |
| Intake-brief cost per verified request | <$0.01 |
| Customer-side AI share of org AI cost | <25% (alert above) |

## 6. Risks & Mitigations

- **Public AI endpoint abuse**: Turnstile, rate limits, verify-before-LLM, burst caps. Public AI endpoints get farmed within weeks — assume it.
- **UK GDPR**: prompts/photos contain personal data; retention limits, access controls, privacy notice covering AI processing (Delivery Plan compliance task).
- **App-store-first instinct** (internal): the app's audience is repeat customers; the QR must never route to a store listing. This is a locked product decision — challenge only with conversion data.
- **Scope creep beyond parity**: payments ship per [PRD-Online-Payments.md](PRD-Online-Payments.md) (Stripe Connect, no take-rate); resist adding financing, instalments or direct debit during beta — log demand instead. Parity bar tracked in [Tradify-Parity-Checklist.md](Tradify-Parity-Checklist.md).

## 7. Out of Scope / Future

Payments beyond the payments PRD (take-rate, financing, BACS), customer messaging templates, tradie review/ratings capture, landlord/property-manager multi-property accounts (the natural Team-tier customer story — revisit at launch).
