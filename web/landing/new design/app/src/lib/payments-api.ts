import { SubscribeApiError, type TradeSession } from '@/lib/subscribe-api'

const API: string = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_DEMO_API_URL ?? ''

export interface ConnectSession {
  client_secret: string
  expires_at: number
  stripe_account_id: string
  publishable_key: string
}

export async function createDashboardSession(session: TradeSession): Promise<ConnectSession> {
  const res = await fetch(`${API}/payments/connect/session`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${session.accessToken}`,
      'X-Tenant-ID': session.tenantId,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ components: 'dashboard' }),
  })
  if (!res.ok) {
    let detail = ''
    try {
      const body = (await res.json()) as { detail?: unknown }
      detail = typeof body.detail === 'string' ? body.detail : ''
    } catch {
      // Use the status-based message below for non-JSON responses.
    }
    throw new SubscribeApiError(
      res.status === 401
        ? 'Your session has expired. Please sign in again.'
        : detail || 'Stripe activity could not be loaded. Please try again.',
      res.status,
    )
  }
  return (await res.json()) as ConnectSession
}
