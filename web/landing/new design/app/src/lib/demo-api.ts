/**
 * Public "Try the AI" demo — typed contract for the demo quote endpoints.
 *
 * Base URL comes from VITE_DEMO_API_URL. In dev it is unset/empty and calls go
 * same-origin to `/demo/...`, which vite proxies to the API (see vite.config.ts).
 * In production set VITE_DEMO_API_URL to the API origin (which must allow this
 * origin in CORS), or front it with a same-origin `/demo` proxy and leave empty.
 */

export interface DemoLineItem {
  description: string
  quantity: number
  unit: string
  unit_price: number
  total: number
  ai_generated: boolean
}

export interface DemoQuoteAi {
  confidence: number
  warnings: string[]
  assumptions: string[]
  notes: string | null
}

export interface DemoQuote {
  line_items: DemoLineItem[]
  subtotal: number
  vat_rate: number
  vat_amount: number
  total: number
  ai: DemoQuoteAi
  retrieval_status: string
  generation_seconds: number
}

export interface GenerateQuoteRequest {
  description: string
  property_type?: string
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
}

export interface RefineQuoteRequest {
  description: string
  property_type?: string
  instructions: string
  /** Echo back the current line items so backend-side edits are preserved. */
  line_items: DemoLineItem[]
}

export class DemoApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'DemoApiError'
    this.status = status
  }
}

const API: string = import.meta.env.VITE_DEMO_API_URL ?? ''
const TIMEOUT_MS = 60_000

/** UTM params forwarded on generate so the backend can attribute the demo. */
export function captureUtm(): Pick<
  GenerateQuoteRequest,
  'utm_source' | 'utm_medium' | 'utm_campaign'
> {
  const out: Pick<GenerateQuoteRequest, 'utm_source' | 'utm_medium' | 'utm_campaign'> = {}
  if (typeof window === 'undefined') return out
  const params = new URLSearchParams(window.location.search)
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign'] as const) {
    const value = params.get(key)
    if (value) out[key] = value
  }
  return out
}

/** Best-effort extraction of FastAPI's `detail` field (string or 422 array). */
function extractDetail(data: unknown): string {
  if (!data || typeof data !== 'object') return ''
  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e) =>
        e && typeof e === 'object'
          ? ((e as { msg?: unknown }).msg ?? '')
          : String(e),
      )
      .filter(Boolean)
      .join(' · ')
  }
  return ''
}

function fallbackMessage(status: number): string {
  if (status === 429) return 'Too many requests — give it a few seconds and try again.'
  if (status === 502) return 'The AI is busy right now — try again in a moment.'
  if (status >= 500) return 'Something went wrong on our side — please try again.'
  return 'That did not work — check the description and try again.'
}

async function postJson(path: string, body: unknown, signal?: AbortSignal): Promise<DemoQuote> {
  // Own controller for the 60s timeout, chained to the caller's signal so
  // unmounting the component cancels the in-flight request.
  const timeout = new AbortController()
  const timer = setTimeout(() => timeout.abort(), TIMEOUT_MS)
  const onAbort = () => timeout.abort()
  signal?.addEventListener('abort', onAbort, { once: true })
  try {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: timeout.signal,
    })
    if (!res.ok) {
      let detail = ''
      try {
        detail = extractDetail(await res.json())
      } catch {
        // non-JSON error body — fall through to the status-based message
      }
      throw new DemoApiError(detail || fallbackMessage(res.status), res.status)
    }
    return (await res.json()) as DemoQuote
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

export function generateQuote(req: GenerateQuoteRequest, signal?: AbortSignal): Promise<DemoQuote> {
  return postJson('/demo/quotes/generate', req, signal)
}

export function refineQuote(req: RefineQuoteRequest, signal?: AbortSignal): Promise<DemoQuote> {
  return postJson('/demo/quotes/refine', req, signal)
}
