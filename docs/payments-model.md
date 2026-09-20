# Payments Money Model — My Trade Portal

This document describes, in factual terms, how money moves through My Trade
Portal. It is written for legal review and for incorporation into the platform
Terms & Conditions, tradesperson terms, and customer-facing payment pages. The
engineering decision record is
[ADR-003 — Stripe Connect Express](decisions/ADR-003-stripe-connect-express.md);
this document is the prose description of that model.

## 1. Two separate money flows

My Trade Portal involves exactly two money flows, operated by two different
regulated providers. The flows never mix.

| Flow | Provider | Who is paid | Provider's role |
|---|---|---|---|
| Customer → tradesperson (payment for trade work: quotes, jobs, invoices) | **Stripe Connect** | The tradesperson, into their own Stripe Express connected account | Stripe processes the payment and settles funds to the tradesperson |
| Tradesperson → My Trade Portal (SaaS subscription) | **Paddle** | My Trade Portal | Paddle is merchant of record for the subscription |

A customer payment for trade work must never touch the platform's Paddle
balance, and subscription billing never touches Stripe Connect.

## 2. Customer → tradesperson payments (Stripe Connect)

### 2.1 Structure

- Each tradesperson who accepts online card payments completes Stripe's
  identity verification (KYC) once, inside the app, via Stripe Connect
  **Express** onboarding. The contractual relationship for receiving card
  payments is between the tradesperson and Stripe.
- Payments are processed as **destination charges**: the customer is charged
  and the funds are destined for the tradesperson's connected account. The
  platform instructs the charge but the funds settle to the tradesperson's
  Stripe balance.
- **The platform never holds customer money.** Funds do not pass through a
  platform-owned account, and the platform takes no commission or percentage
  of customer payments (no take-rate). Stripe's card-processing fees are
  charged to the tradesperson and passed through transparently.
- The platform is not a party to the contract for the underlying trade work;
  that contract is between the tradesperson and their customer. The platform
  provides invoicing and payment-collection tooling only.
- Card details are entered into Stripe-hosted fields (Stripe Payment Element,
  Apple Pay / Google Pay). Card numbers never touch platform servers.

### 2.2 Payout timing

- Stripe settles funds from each charge to the tradesperson's Stripe balance
  and pays out to the tradesperson's nominated UK bank account on Stripe's
  standard Express payout schedule for the UK (typically 2 business days on a
  rolling basis once the account is established; the first payout after
  onboarding can take longer — commonly 7–14 days — while Stripe completes
  account verification).
- Payout timing is controlled by Stripe and the tradesperson's account
  standing, not by the platform. The platform surfaces payout status
  (e.g. `payout.paid` webhook events) for reconciliation only.

### 2.3 Refunds

- Refunds of card-paid invoices are **initiated by the tradesperson** from the
  invoice view. The platform instructs Stripe to refund the original charge;
  the refunded amount is debited from the tradesperson's Stripe balance (or
  recovered from their bank account by Stripe if the balance is
  insufficient). Stripe's original processing fees are not returned on a
  refund, per Stripe's pricing.
- The platform supports full refunds of card-paid invoices. Partial refunds
  and deposits are out of scope for the current release.
- Payments made outside Stripe (bank transfer, cash) are refunded directly
  between tradesperson and customer; the platform has no involvement.

### 2.4 Disputes (chargebacks)

- A cardholder dispute is a matter between the cardholder, their bank, and the
  tradesperson as the payee of record. The disputed amount plus Stripe's
  dispute fee are debited from the tradesperson's Stripe balance when the
  dispute is opened, per Stripe's terms.
- The tradesperson is responsible for submitting dispute evidence through
  Stripe. The platform detects disputes (`charge.dispute.created` webhook)
  and alerts the tradesperson, but does not manage or adjudicate disputes and
  bears no liability for their outcome.

### 2.5 Surcharging

- Consumer (B2C) card surcharging is banned in the UK and is disabled on the
  platform. Any B2B surcharging is off by default and would require legal
  review before being enabled.

## 3. Tradesperson → platform subscription (Paddle)

- The platform's SaaS subscription is billed by **Paddle as merchant of
  record**. Paddle is the seller of the subscription for VAT and consumer-law
  purposes; Paddle's checkout, invoicing, and dunning apply.
- Subscription billing is entirely separate from customer payments: no
  customer card details, payouts, refunds, or disputes for trade work ever
  involve Paddle.

## 4. No-card-payments fallback (bank transfer)

- Online card payments are optional per tradesperson. If a tradesperson has
  not connected Stripe, or turns off online payments for an invoice, the
  invoice (email, PDF, and customer portal view) instead presents the
  **tradesperson's own bank-transfer details** — account name, sort code, and
  account number, drawn from the tradesperson's settings — with the invoice
  number as the suggested payment reference.
- Bank transfers settle directly between the customer's bank and the
  tradesperson's bank. The platform does not process, hold, or reconcile
  these funds; the tradesperson marks the invoice as paid manually. Customers
  without access to card payment can always pay this way.

## 5. Compliance summary

- **FCA-regulated money flow:** handled by Stripe under its own permissions
  via Stripe Connect; the platform is not in the flow of funds.
- **PCI DSS:** Stripe-hosted payment fields only; no cardholder data is
  stored, processed, or transmitted by platform servers.
- **Data protection:** payment metadata (payer name, amount, invoice
  reference) is processed under the platform privacy notice and retention
  schedule; Stripe and Paddle act as independent controllers/processors for
  their respective flows under their own terms.
- **Webhooks:** payment state (succeeded, refunded, disputed, payout paid) is
  ingested via idempotent, signature-verified webhook handlers so invoice
  status reflects the money flow accurately.
