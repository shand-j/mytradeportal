# Go-live checklist — Stripe payments (issue #44)

Use this checklist after webhook safety #30 and fee/refund/dispute liability #355
are resolved:
- production `STRIPE_*` config in Railway
- mobile OTA publish for the payment-keyed frontend
- sandbox → live smoke evidence

Never attach raw environment exports, secret values, tokens, card data, or
customer PII to the issue.

## 1) Set production Stripe env in Railway (`api` service)

Set these in the **production** Railway environment, then redeploy `api`:

- `STRIPE_SECRET_KEY` (`sk_live_...` or restricted key with required write scopes)
- `STRIPE_WEBHOOK_SECRET` (platform webhook endpoint secret)
- `STRIPE_CONNECT_WEBHOOK_SECRET` (Connect webhook endpoint secret)
- `STRIPE_CONNECT_CLIENT_ID`
- `STRIPE_PUBLISHABLE_KEY` (`pk_live_...`)

Then verify:

```bash
curl -fsS https://<api-domain>/health
curl -fsS https://<api-domain>/ready
```

## 2) Publish frontend keys + mobile OTA

### Landing pay page

Set `VITE_STRIPE_PUBLISHABLE_KEY=pk_live_...` for the landing app build/deploy.

### Mobile OTA

From the repository root:

```bash
cd mobile
npx eas-cli update --branch production --message "chore: stripe live publishable key rollout"
```

Record the EAS update group ID and confirm the trade Payments screen loads without config errors.

## 3) Sandbox smoke (must be green before live-card check)

Run the deployed write suite against staging (or trigger `.github/workflows/staging-e2e.yml`).

Minimum pass criteria from Delivery Plan 0.11:
- Connect onboarding mirror passes
- invoice send → webhook settle path passes
- staff `invoice_paid` notification exists
- refund webhook path remains idempotent

## 4) Live-mode manual smoke (production)

Run once with a low-value real invoice:

1. Tradie Connect onboarding completes (`/payments/status` shows `connected=true`, `charges_enabled=true`).
2. Send invoice with card payments enabled.
3. Customer opens branded `/pay/:token` page and pays.
4. Stripe webhook marks invoice `paid` automatically.
5. Tradie receives `invoice_paid` notification.
6. `invoice_paid` outcome event is trace-linked.

Trace-link verification (example SQL):

~~~sql
SELECT
  feature,
  raw_payload->>'outcome' AS outcome,
  trace_id,
  quote_id,
  raw_payload AS payload
FROM ai_call_events
WHERE feature = 'outcome' AND raw_payload->>'outcome' = 'invoice_paid'
ORDER BY created_at DESC
LIMIT 5;
~~~

Expected: latest row has non-null `trace_id` and `payload` containing `invoice_id`.

## 5) Evidence to attach to issue #44

- Redacted Railway evidence showing only that the required `STRIPE_*` variable
  names are present; never include values or exports
- EAS OTA publish link/group ID
- Sandbox run link (staging-e2e workflow)
- Live smoke proof:
  - paid invoice screenshot on `/invoice/:token`
  - tradie notification screenshot
  - webhook success log snippet
  - `ai_call_events` row snippet showing `outcome=invoice_paid` with `trace_id`
