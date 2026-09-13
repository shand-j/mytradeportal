/**
 * Typed client for the tenant-portal API contract.
 *
 * Public endpoints (no auth): public-config, quote-request submission +
 * uploads, guest triage thread, magic-link request/consume. Authenticated
 * endpoints go through apiFetch (session.ts) with the customer JWT.
 *
 * Base URL: VITE_API_URL, empty means same-origin (dev proxy / gateway).
 *
 * The public-config endpoint predates the portal contract and serialises
 * some fields under camelCase aliases (logoUrl, primaryColor,
 * businessServices, contactPhone) — the normaliser below accepts both
 * spellings so the portal works against today's API and the contract one.
 */

import { API_BASE, apiFetch, SessionExpiredError } from './session'

export class PortalApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'PortalApiError'
    this.status = status
  }
}

export { SessionExpiredError }

/* ------------------------------------------------------------------ */
/* Public config                                                       */
/* ------------------------------------------------------------------ */

export interface PortalConfig {
  slug: string
  code: string | null
  name: string
  logo_url: string | null
  primary_color: string
  secondary_color: string
  service_categories: string[]
  phone: string | null
  address: string | null
  review_url?: string | null
  reply_email?: string | null
}

function pick<T>(raw: Record<string, unknown>, ...keys: string[]): T | undefined {
  for (const key of keys) {
    const value = raw[key]
    if (value !== undefined && value !== null) return value as T
  }
  return undefined
}

function normalizeConfig(raw: Record<string, unknown>): PortalConfig {
  return {
    slug: String(raw.slug ?? ''),
    code: pick<string>(raw, 'code') ?? null,
    name: String(raw.name ?? ''),
    logo_url: pick<string>(raw, 'logo_url', 'logoUrl') ?? null,
    primary_color: pick<string>(raw, 'primary_color', 'primaryColor') ?? '#0F1E26',
    secondary_color: pick<string>(raw, 'secondary_color', 'secondaryColor') ?? '#0F1E26',
    service_categories:
      pick<string[]>(raw, 'service_categories', 'serviceCategories', 'business_services', 'businessServices') ??
      [],
    phone: pick<string>(raw, 'phone', 'contact_phone', 'contactPhone') ?? null,
    address: pick<string>(raw, 'address') ?? null,
    review_url: pick<string>(raw, 'review_url', 'reviewUrl') ?? null,
    reply_email: pick<string>(raw, 'reply_email', 'replyEmail') ?? null,
  }
}

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
  if (res.status === 404) throw new PortalApiError(detail || 'Not found.', 404)
  if (res.status === 429) throw new PortalApiError('Too many attempts — try again in a little while.', 429)
  throw new PortalApiError(detail || 'Something went wrong — please try again.', res.status)
}

export async function fetchPublicConfig(slug: string): Promise<PortalConfig> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/businesses/${encodeURIComponent(slug)}/public-config`)
  } catch {
    throw new PortalApiError('Network error — check your connection and try again.', 0)
  }
  if (!res.ok) await parseError(res)
  return normalizeConfig((await res.json()) as Record<string, unknown>)
}

/** Resolve a 6-digit business code to its config (www-mode code entry). */
export async function fetchPublicConfigByCode(code: string): Promise<PortalConfig> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/businesses/by-code/${encodeURIComponent(code)}/public-config`)
  } catch {
    throw new PortalApiError('Network error — check your connection and try again.', 0)
  }
  if (!res.ok) await parseError(res)
  return normalizeConfig((await res.json()) as Record<string, unknown>)
}

/* ------------------------------------------------------------------ */
/* Quote requests (public)                                             */
/* ------------------------------------------------------------------ */

export type EntryChannel = 'qr' | 'code' | 'widget' | 'direct'

export interface QuoteRequestInput {
  name: string
  email: string
  phone?: string
  category?: string
  description: string
  media_urls: string[]
  preferred_dates: { date: string }[]
  sync_check: boolean
  entry_channel: EntryChannel
}

export interface AiCheck {
  status: 'questions' | 'ok' | 'unavailable'
  question?: string
  thread_token?: string
  thread_expires_at?: string
}

export interface QuoteRequestAck {
  id: string
  status: string
  reference: string
  ai_check?: AiCheck
}

export async function submitQuoteRequest(
  slug: string,
  input: QuoteRequestInput,
): Promise<QuoteRequestAck> {
  const res = await fetch(`${API_BASE}/businesses/${encodeURIComponent(slug)}/quote-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contact: { name: input.name, email: input.email, phone: input.phone || null },
      category: input.category || null,
      title: input.description.slice(0, 80),
      raw_text: input.description,
      media_urls: input.media_urls,
      preferred_dates: input.preferred_dates,
      sync_check: input.sync_check,
      entry_channel: input.entry_channel,
    }),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as QuoteRequestAck
}

/** Upload photos for a quote request; returns URLs to pass as media_urls. */
export async function uploadQuoteRequestImages(slug: string, files: File[]): Promise<string[]> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  const res = await fetch(
    `${API_BASE}/businesses/${encodeURIComponent(slug)}/quote-requests/uploads`,
    { method: 'POST', body: form },
  )
  if (!res.ok) await parseError(res)
  const data = (await res.json()) as { urls: string[] }
  return data.urls
}

/* ------------------------------------------------------------------ */
/* Guest triage thread (public, thread_token bearer)                   */
/* ------------------------------------------------------------------ */

export interface ThreadMessage {
  id: string
  sender_role: 'customer' | 'ai' | 'business'
  body: string
  created_at: string
}

export async function getGuestThread(
  quoteRequestId: string,
  threadToken: string,
): Promise<{ messages: ThreadMessage[] }> {
  const res = await fetch(`${API_BASE}/public/threads/${encodeURIComponent(quoteRequestId)}/messages`, {
    headers: { Authorization: `Bearer ${threadToken}` },
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as { messages: ThreadMessage[] }
}

export async function postGuestMessage(
  quoteRequestId: string,
  threadToken: string,
  body: string,
): Promise<{ message: ThreadMessage; ai_reply?: { body: string }; closed?: boolean }> {
  const res = await fetch(`${API_BASE}/public/threads/${encodeURIComponent(quoteRequestId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${threadToken}` },
    body: JSON.stringify({ body }),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as {
    message: ThreadMessage
    ai_reply?: { body: string }
    closed?: boolean
  }
}

/* ------------------------------------------------------------------ */
/* Magic-link auth (public)                                            */
/* ------------------------------------------------------------------ */

export interface MagicAuthResponse {
  access_token: string
  token_type: 'bearer'
  customer: { id: string; full_name: string; email: string }
  expires_at: string
}

export async function consumeMagicToken(token: string): Promise<MagicAuthResponse> {
  const res = await fetch(`${API_BASE}/customer/auth/magic`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as MagicAuthResponse
}

/** Always resolves (202 generic) — never reveals whether the email exists. */
export async function requestMagicLink(email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/customer/auth/magic/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok && res.status === 429) await parseError(res)
}

/* ------------------------------------------------------------------ */
/* Authenticated customer API                                          */
/* ------------------------------------------------------------------ */

export interface CustomerMe {
  id: string
  full_name: string
  email: string
}

export interface CustomerLineItem {
  id: string
  description: string
  quantity: string
  unit: string
  unit_price: string
  total: string
}

export interface CustomerQuote {
  id: string
  title: string
  description: string | null
  status: string
  subtotal: string
  vat_rate: string
  vat_amount: string
  total: string
  valid_until: string | null
  sent_at: string | null
  approved_at: string | null
  created_at: string
  updated_at: string
  quote_request_id: string | null
  accepted_dates?: string[]
  line_items: CustomerLineItem[]
}

export interface CustomerInvoice {
  id: string
  invoice_number: string
  status: string
  issue_date: string
  due_date: string | null
  subtotal: string
  vat_rate: string
  vat_amount: string
  total: string
  paid_at: string | null
  notes: string | null
  line_items: CustomerLineItem[]
  /** Pending backend: online-pay handoff for the portal pay flow. */
  payment_url?: string | null
  payment_client_secret?: string | null
}

export interface CustomerQuoteRequest {
  id: string
  status: string
  raw_text: string | null
  urgency: string
  quote_id: string | null
  created_at: string
}

export interface PortalCommunication {
  id: string
  quote_request_id: string | null
  channel: string
  sender_role: 'customer' | 'ai' | 'business' | string
  body: string | null
  created_at: string
}

export interface CustomerAppointment {
  id: string
  title: string
  starts_at: string
  ends_at: string
  status: string
}

async function authed<T>(slug: string, path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(slug, path, init)
  if (!res.ok) await parseError(res)
  return (await res.json()) as T
}

export const getMe = (slug: string) => authed<CustomerMe>(slug, '/customer/me')

export const listQuoteRequests = (slug: string) =>
  authed<CustomerQuoteRequest[]>(slug, '/customer/quote-requests')

export const listQuotes = (slug: string) => authed<CustomerQuote[]>(slug, '/customer/quotes')

export const acceptQuote = (slug: string, quoteId: string, preferredDates?: { date: string }[]) =>
  authed<CustomerQuote>(slug, `/customer/quotes/${encodeURIComponent(quoteId)}/accept`, {
    method: 'POST',
    body: JSON.stringify({ preferred_dates: preferredDates }),
  })

export const rejectQuote = (slug: string, quoteId: string) =>
  authed<CustomerQuote>(slug, `/customer/quotes/${encodeURIComponent(quoteId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({}),
  })

export const listInvoices = (slug: string) => authed<CustomerInvoice[]>(slug, '/customer/invoices')

export const getInvoice = (slug: string, invoiceId: string) =>
  authed<CustomerInvoice>(slug, `/customer/invoices/${encodeURIComponent(invoiceId)}`)

export const listAppointments = (slug: string) =>
  authed<CustomerAppointment[]>(slug, '/customer/appointments')

export const listCommunications = (slug: string, quoteRequestId: string) =>
  authed<PortalCommunication[]>(
    slug,
    `/communications?quote_request_id=${encodeURIComponent(quoteRequestId)}`,
  )

export const postCommunication = (slug: string, quoteRequestId: string, body: string) =>
  authed<PortalCommunication>(slug, '/communications', {
    method: 'POST',
    body: JSON.stringify({ quote_request_id: quoteRequestId, body, channel: 'chat' }),
  })
