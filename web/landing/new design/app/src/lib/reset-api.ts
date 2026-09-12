/**
 * Password-reset client for the landing site's /reset-password page.
 *
 * Base URL comes from VITE_API_URL (falling back to VITE_DEMO_API_URL, which
 * points at the same API origin). When both are empty, calls go same-origin —
 * pair that with a dev proxy or a same-origin gateway in front of the API.
 * The API must allow this origin in CORS (ALLOWED_ORIGINS).
 */

export interface ResetTokenInfo {
  email: string
  expires_at: string
}

export class ResetApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ResetApiError'
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
  if (res.status === 400) throw new ResetApiError(detail || 'Invalid or expired token', 400)
  if (res.status === 429) throw new ResetApiError('Too many attempts — try again later.', 429)
  throw new ResetApiError(detail || 'Something went wrong — please try again.', res.status)
}

/** Look up the account behind a reset token. Does not consume the token. */
export async function inspectResetToken(token: string): Promise<ResetTokenInfo> {
  const res = await fetch(`${API}/auth/password-reset/inspect?token=${encodeURIComponent(token)}`)
  if (!res.ok) await parseError(res)
  return (await res.json()) as ResetTokenInfo
}

/** Complete the reset. Consumes the token on success. */
export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  const res = await fetch(`${API}/auth/password-reset/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  })
  if (!res.ok) await parseError(res)
}
