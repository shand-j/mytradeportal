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
