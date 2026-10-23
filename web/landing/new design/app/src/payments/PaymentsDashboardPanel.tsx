import { useCallback, useEffect, useMemo, useState } from 'react'
import { loadConnectAndInitialize } from '@stripe/connect-js'
import {
  ConnectBalances,
  ConnectComponentsProvider,
  ConnectNotificationBanner,
  ConnectPayouts,
} from '@stripe/react-connect-js'
import { usePageMeta } from '@/hooks/usePageMeta'
import { createDashboardSession, type ConnectSession } from '@/lib/payments-api'
import {
  SubscribeApiError,
  loginTrade,
  type TradeSession,
} from '@/lib/subscribe-api'

const SESSION_KEY = 'mtp_subscribe_session'

function loadSession(): TradeSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const session = JSON.parse(raw) as TradeSession
    return session.accessToken && session.tenantId ? session : null
  } catch {
    return null
  }
}

function saveSession(session: TradeSession | null): void {
  try {
    if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session))
    else window.localStorage.removeItem(SESSION_KEY)
  } catch {
    // The login still works for this page view when storage is unavailable.
  }
}

export function PaymentsDashboardPanel() {
  usePageMeta(
    'Stripe activity — My Trade Portal',
    'View your Stripe balance, payouts and account requirements from My Trade Portal.',
  )
  const [session, setSession] = useState<TradeSession | null>(() => loadSession())

  const signOut = () => {
    saveSession(null)
    setSession(null)
  }

  if (!session) {
    return (
      <LoginView
        onSignedIn={(next) => {
          saveSession(next)
          setSession(next)
        }}
      />
    )
  }

  return <DashboardView session={session} onSessionExpired={signOut} onSignOut={signOut} />
}

function LoginView({ onSignedIn }: { onSignedIn: (session: TradeSession) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const canSubmit = email.trim().length > 0 && password.length > 0 && !submitting

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      onSignedIn(await loginTrade(email.trim(), password))
    } catch (err) {
      setError(
        err instanceof SubscribeApiError ? err.message : 'Something went wrong — please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Payments</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Sign in to Stripe activity
      </h1>
      <p className="mt-[var(--space-sm)] text-[14px] leading-relaxed text-[var(--muted)]">
        Use the email and password you registered with in the My Trade Portal app.
      </p>
      <form onSubmit={onSubmit} className="mt-[var(--space-lg)] space-y-[var(--space-md)]">
        <div>
          <label htmlFor="payments-email" className="spec-label text-[var(--muted)]">
            Email
          </label>
          <input
            id="payments-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
          />
        </div>
        <div>
          <label htmlFor="payments-password" className="spec-label text-[var(--muted)]">
            Password
          </label>
          <input
            id="payments-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
          />
        </div>
        {error && (
          <p
            role="alert"
            className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-3.5 text-[13.5px] leading-relaxed"
          >
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={!canSubmit}
          className="chip chip--fill w-full justify-center disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

function DashboardView({
  session,
  onSessionExpired,
  onSignOut,
}: {
  session: TradeSession
  onSessionExpired: () => void
  onSignOut: () => void
}) {
  const [connectSession, setConnectSession] = useState<ConnectSession | null>(null)
  const [error, setError] = useState('')

  const loadSession = useCallback(async () => {
    setError('')
    setConnectSession(null)
    try {
      setConnectSession(await createDashboardSession(session))
    } catch (err) {
      if (err instanceof SubscribeApiError && err.status === 401) {
        onSessionExpired()
        return
      }
      setError(
        err instanceof SubscribeApiError
          ? err.message
          : 'Stripe activity could not be loaded — check your connection and try again.',
      )
    }
  }, [onSessionExpired, session])

  useEffect(() => {
    let cancelled = false
    createDashboardSession(session)
      .then((next) => {
        if (!cancelled) setConnectSession(next)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof SubscribeApiError && err.status === 401) {
          onSessionExpired()
          return
        }
        setError(
          err instanceof SubscribeApiError
            ? err.message
            : 'Stripe activity could not be loaded — check your connection and try again.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [onSessionExpired, session])

  return (
    <section className="w-full max-w-[1100px]">
      <div className="flex flex-wrap items-end justify-between gap-[var(--space-md)]">
        <div>
          <p className="spec-label text-[var(--muted)]">Payments</p>
          <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.8rem,4vw,2.75rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            Stripe activity
          </h1>
          <p className="mt-[var(--space-sm)] text-[14px] text-[var(--muted)]">
            Signed in as <span className="font-semibold text-[var(--ink)]">{session.email}</span>
            {' · '}
            <button
              type="button"
              onClick={onSignOut}
              className="underline decoration-[var(--accent)] decoration-2 underline-offset-4 hover:text-[var(--ink)]"
            >
              Not you? Sign out
            </button>
          </p>
        </div>
        <button type="button" onClick={() => void loadSession()} className="chip">
          Refresh activity
        </button>
      </div>
      <p className="mt-[var(--space-md)] max-w-[70ch] text-[14px] leading-relaxed text-[var(--muted)]">
        Your customer payments, balance and payouts are managed securely by Stripe. This page is
        separate from your My Trade Portal subscription.
      </p>

      {error && (
        <p
          role="alert"
          className="mt-[var(--space-lg)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
        >
          {error}
        </p>
      )}
      {!connectSession && !error && (
        <div className="mt-[var(--space-xl)] flex items-center gap-3" role="status">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
          <p className="text-[14px] text-[var(--muted)]">Loading Stripe activity…</p>
        </div>
      )}
      {connectSession && <DashboardComponents session={session} initial={connectSession} />}
    </section>
  )
}

function DashboardComponents({
  session,
  initial,
}: {
  session: TradeSession
  initial: ConnectSession
}) {
  const [error, setError] = useState('')
  const fetchClientSecret = useCallback(
    async () => (await createDashboardSession(session)).client_secret,
    [session],
  )
  const connectInstance = useMemo(
    () =>
      loadConnectAndInitialize({
        publishableKey: initial.publishable_key,
        fetchClientSecret,
        appearance: { variables: { colorPrimary: '#17212b' } },
      }),
    [fetchClientSecret, initial.publishable_key],
  )
  const onLoadError = () => setError('A Stripe component could not load. Refresh to try again.')

  return (
    <ConnectComponentsProvider connectInstance={connectInstance}>
      <div className="mt-[var(--space-lg)] space-y-[var(--space-lg)]">
        {error && (
          <p role="alert" className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4">
            {error}
          </p>
        )}
        <ConnectNotificationBanner onLoadError={onLoadError} />
        <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-4 md:p-6">
          <h2 className="mb-[var(--space-md)] font-display text-[1.35rem] font-bold uppercase">
            Balance
          </h2>
          <ConnectBalances onLoadError={onLoadError} />
        </section>
        <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-4 md:p-6">
          <h2 className="mb-[var(--space-md)] font-display text-[1.35rem] font-bold uppercase">
            Payouts
          </h2>
          <ConnectPayouts onLoadError={onLoadError} />
        </section>
      </div>
    </ConnectComponentsProvider>
  )
}
