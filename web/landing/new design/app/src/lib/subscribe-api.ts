/**
 * Trade-account auth + billing client for the landing site's /subscribe page.
 *
 * Flow: POST /auth/token (same bare-domain email+password login the mobile
 * app uses — the API resolves the tenant from the email) → GET /billing/plans
 * (public catalog) → POST /billing/checkout with Authorization: Bearer +
 * X-Tenant-ID → browser follows the returned checkout_url (the Paddle
 * checkout host page — this page, with ?_ptxn appended by Paddle).
 *
 * Base URL comes from VITE_API_URL (falling back to VITE_DEMO_API_URL), same
 * convention as reset-api.ts / invite-api.ts. The API must allow this origin
 * in CORS (ALLOWED_ORIGINS) — www.mytradeportal.co.uk is covered.
 */

export class SubscribeApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'SubscribeApiError'
    this.status = status
  }
}

const API: string = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_DEMO_API_URL ?? ''

/** Best-effort extraction of FastAPI's `detail` field (string or 422 array). */
function extractDetail(data: unknown): string {
  if (!data || typeof data !== 'object') return ''
  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e === 'object' ? ((e as { msg?: unknown }).msg ?? '') : String(e)))
      .filter(Boolean)
      .join(' · ')
  }
  return ''
}

async function parseError(res: Response): Promise<never> {
  let detail = ''
  try {
    detail = extractDetail(await res.json())
  } catch {
    // non-JSON error body — fall through to the status-based message
  }
  if (res.status === 401) throw new SubscribeApiError(detail || 'Invalid email or password.', 401)
  if (res.status === 429) throw new SubscribeApiError('Too many attempts — try again later.', 429)
  throw new SubscribeApiError(detail || 'Something went wrong — please try again.', res.status)
}

/* ------------------------------------------------------------------ */
/* Trade auth (POST /auth/token)                                       */
/* ------------------------------------------------------------------ */

export interface TradeSession {
  accessToken: string
  tenantId: string
  tenantSlug: string
  email: string
  fullName: string
}

interface TokenResponseBody {
  access_token: string
  token_type: string
  tenant_slug: string
  user: {
    id: string
    tenant_id: string
    email: string
    full_name: string
    role: string
  }
}

/** Authenticate a tradesperson. The API resolves the tenant from the email. */
export async function loginTrade(email: string, password: string): Promise<TradeSession> {
  const res = await fetch(`${API}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) await parseError(res)
  const data = (await res.json()) as TokenResponseBody
  return {
    accessToken: data.access_token,
    tenantId: data.user.tenant_id,
    tenantSlug: data.tenant_slug,
    email: data.user.email,
    fullName: data.user.full_name,
  }
}

/* ------------------------------------------------------------------ */
/* Billing                                                             */
/* ------------------------------------------------------------------ */

/** One tier from GET /billing/plans (public — mirrors app.plans). */
export interface BillingPlan {
  key: string
  name: string
  monthly_price_gbp: number
  annual_price_gbp: number
  seats: number
  features: string[]
  featured: boolean
  trial_days: number
}

export async function fetchBillingPlans(): Promise<BillingPlan[]> {
  const res = await fetch(`${API}/billing/plans`)
  if (!res.ok) await parseError(res)
  return (await res.json()) as BillingPlan[]
}

export interface SubscriptionState {
  id: string
  plan_key: string
  status: string
  trial_ends_at: string | null
  current_period_end: string | null
  seats: number
  seats_in_use: number
}

/** Subscription statuses where the tenant already has app access. */
export const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['trialing', 'active', 'past_due'])

function authedHeaders(session: TradeSession): HeadersInit {
  return {
    Authorization: `Bearer ${session.accessToken}`,
    'X-Tenant-ID': session.tenantId,
  }
}

/** GET /billing/subscription — null when the tenant has no subscription row. */
export async function fetchSubscription(session: TradeSession): Promise<SubscriptionState | null> {
  const res = await fetch(`${API}/billing/subscription`, { headers: authedHeaders(session) })
  if (!res.ok) await parseError(res)
  return (await res.json()) as SubscriptionState | null
}

export interface CheckoutResponse {
  transaction_id: string
  checkout_url: string
}

export async function createCheckout(
  session: TradeSession,
  planKey: string,
  interval: 'month' | 'year',
  successUrl: string,
): Promise<CheckoutResponse> {
  const res = await fetch(`${API}/billing/checkout`, {
    method: 'POST',
    headers: { ...authedHeaders(session), 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_key: planKey, interval, success_url: successUrl }),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as CheckoutResponse
}

/** Mint a Paddle customer-portal URL for an existing subscription. */
export async function createPortalSession(session: TradeSession): Promise<{ portal_url: string }> {
  const res = await fetch(`${API}/billing/portal-session`, {
    method: 'POST',
    headers: authedHeaders(session),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as { portal_url: string }
}
