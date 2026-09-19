/**
 * Public quote/invoice client for the landing site's /quote/:token and
 * /invoice/:token pages — secure web views for customers without the app.
 *
 * Same origin-resolution pattern as reset-api.ts: base URL from VITE_API_URL
 * (falling back to VITE_DEMO_API_URL); empty means same-origin. The API must
 * allow this origin in CORS (ALLOWED_ORIGINS).
 */

export interface PublicDocTenant {
  name: string
  brand_color: string
  logo_url: string | null
  reply_email: string | null
}

export interface PublicDocLine {
  description: string
  quantity: string
  unit: string
  unit_price: string
  total: string
}

export interface PublicDocPaymentDetails {
  account_name: string
  sort_code: string
  account_number: string
  reference: string
}

/** Coarse time-of-day window for a preferred visit date (availability is by date only). */
export type QuoteTimeWindow = 'morning' | 'afternoon'

/** One ranked visit-date preference (1st/2nd/3rd choice by array order). */
export interface PublicQuotePreference {
  date: string
  time?: QuoteTimeWindow
}

/** Free/busy status of one date — deliberately coarse, no booking details. */
export type AvailabilityDayStatus = 'available' | 'partial' | 'busy' | 'closed'

export interface PublicAvailabilityDay {
  date: string
  status: AvailabilityDayStatus
}

export interface PublicQuoteAvailability {
  /** Estimated visit length in working hours, when the quote carries one. */
  estimated_hours: number | null
  days: PublicAvailabilityDay[]
}

export interface PublicDocPayload {
  kind: 'quote' | 'invoice'
  status: string
  title: string | null
  description: string | null
  invoice_number: string | null
  customer_first_name: string
  tenant: PublicDocTenant
  lines: PublicDocLine[]
  subtotal: string
  vat_rate: string
  vat_amount: string
  total: string
  currency: string
  sent_at: string | null
  valid_until: string | null
  due_date: string | null
  paid_at: string | null
  payment_url: string | null
  payment_details: PublicDocPaymentDetails | null
  /** The customer's own previously submitted preferred visit dates. */
  accepted_dates?: string[]
}

export class PublicDocsApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'PublicDocsApiError'
    this.status = status
  }
}

const API: string = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_DEMO_API_URL ?? ''

/**
 * Fetch the render payload for a document token. Any failure (unknown,
 * expired or revoked token) comes back from the API as the same 404, surfaced
 * here as `PublicDocsApiError` with status 404 — the page shows one generic
 * invalid-link state either way.
 */
export async function fetchPublicDocument(
  kind: 'quote' | 'invoice',
  token: string,
): Promise<PublicDocPayload> {
  let res: Response
  try {
    res = await fetch(`${API}/public/${kind}/${encodeURIComponent(token)}`)
  } catch {
    throw new PublicDocsApiError('Network error — check your connection and try again.', 0)
  }
  if (res.status === 404) {
    throw new PublicDocsApiError('This link is invalid or has expired.', 404)
  }
  if (res.status === 429) {
    throw new PublicDocsApiError('Too many attempts — try again in a little while.', 429)
  }
  if (!res.ok) {
    throw new PublicDocsApiError('Something went wrong — please try again.', res.status)
  }
  return (await res.json()) as PublicDocPayload
}

async function postPublicQuoteAction(
  token: string,
  action: 'accept' | 'decline',
  body: Record<string, unknown>,
): Promise<PublicDocPayload> {
  let res: Response
  try {
    res = await fetch(`${API}/public/quote/${encodeURIComponent(token)}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new PublicDocsApiError('Network error — check your connection and try again.', 0)
  }
  if (res.status === 404) {
    throw new PublicDocsApiError('This link is invalid or has expired.', 404)
  }
  if (res.status === 409) {
    throw new PublicDocsApiError(
      'This quote has already been responded to — reload the page to see the latest state.',
      409,
    )
  }
  if (res.status === 429) {
    throw new PublicDocsApiError('Too many attempts — try again in a little while.', 429)
  }
  if (!res.ok) {
    throw new PublicDocsApiError('Something went wrong — please try again.', res.status)
  }
  return (await res.json()) as PublicDocPayload
}

/**
 * Accept a quote from the emailed token page. `preferredDates` (up to 3
 * ranked YYYY-MM-DD choices, each with an optional morning/afternoon window)
 * ride on the quote so the electrician sees them when scheduling; the 1st
 * choice also pre-fills the auto-created draft job. Resolves with the
 * refreshed render payload (status becomes `approved`).
 */
export function acceptPublicQuote(
  token: string,
  preferredDates?: PublicQuotePreference[],
): Promise<PublicDocPayload> {
  return postPublicQuoteAction(
    token,
    'accept',
    preferredDates && preferredDates.length > 0 ? { preferred_dates: preferredDates } : {},
  )
}

/** Decline a quote from the emailed token page (status becomes `rejected`). */
export function declinePublicQuote(token: string): Promise<PublicDocPayload> {
  return postPublicQuoteAction(token, 'decline', {})
}

/**
 * Free/busy summary by date for the electrician behind a quote token —
 * coarse statuses only, never booking details. Backs the availability-aware
 * calendar on the quote page.
 */
export async function fetchPublicQuoteAvailability(
  token: string,
  days = 35,
): Promise<PublicQuoteAvailability> {
  let res: Response
  try {
    res = await fetch(
      `${API}/public/quote/${encodeURIComponent(token)}/availability?days=${days}`,
    )
  } catch {
    throw new PublicDocsApiError('Network error — check your connection and try again.', 0)
  }
  if (res.status === 404) {
    throw new PublicDocsApiError('This link is invalid or has expired.', 404)
  }
  if (res.status === 429) {
    throw new PublicDocsApiError('Too many attempts — try again in a little while.', 429)
  }
  if (!res.ok) {
    throw new PublicDocsApiError('Something went wrong — please try again.', res.status)
  }
  return (await res.json()) as PublicQuoteAvailability
}

/**
 * Submit up to 3 ranked visit-date preferences after acceptance (or update
 * them). Stores them on the quote and re-seats the tentative draft job on
 * the 1st choice. Resolves with the stored labels.
 */
export async function submitPublicQuotePreferences(
  token: string,
  preferences: PublicQuotePreference[],
): Promise<{ accepted_dates: string[] }> {
  let res: Response
  try {
    res = await fetch(`${API}/public/quote/${encodeURIComponent(token)}/preferences`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preferences }),
    })
  } catch {
    throw new PublicDocsApiError('Network error — check your connection and try again.', 0)
  }
  if (res.status === 404) {
    throw new PublicDocsApiError('This link is invalid or has expired.', 404)
  }
  if (res.status === 409) {
    throw new PublicDocsApiError(
      'These dates can no longer be updated — contact your electrician directly.',
      409,
    )
  }
  if (res.status === 429) {
    throw new PublicDocsApiError('Too many attempts — try again in a little while.', 429)
  }
  if (!res.ok) {
    throw new PublicDocsApiError('Something went wrong — please try again.', res.status)
  }
  return (await res.json()) as { accepted_dates: string[] }
}
