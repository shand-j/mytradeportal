/**
 * Team-invite client for the landing site's /accept-invite page.
 *
 * Base URL comes from VITE_API_URL (falling back to VITE_DEMO_API_URL, which
 * points at the same API origin), same convention as reset-api.ts.
 */

export interface AcceptInviteResult {
  detail: string
  email: string
}

export class InviteApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'InviteApiError'
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
  if (res.status === 401) throw new InviteApiError(detail || 'Invalid or expired invite link', 401)
  if (res.status === 429) throw new InviteApiError('Too many attempts — try again later.', 429)
  throw new InviteApiError(detail || 'Something went wrong — please try again.', res.status)
}

/** Accept an invite: set the account password. Consumes the token on success. */
export async function acceptInvite(token: string, password: string): Promise<AcceptInviteResult> {
  const res = await fetch(`${API}/users/accept-invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  })
  if (!res.ok) await parseError(res)
  return (await res.json()) as AcceptInviteResult
}
