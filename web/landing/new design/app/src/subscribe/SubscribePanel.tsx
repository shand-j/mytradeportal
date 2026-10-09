import { initializePaddle, type Environments, type Paddle } from '@paddle/paddle-js'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { PricingTiers } from '@/constants/pricing-tiers'
import { usePageMeta } from '@/hooks/usePageMeta'
import { TESTFLIGHT_URL, testflightConfigured } from '@/lib/site'
import {
  ACTIVE_SUBSCRIPTION_STATUSES,
  SubscribeApiError,
  createCheckout,
  createPortalSession,
  fetchBillingPlans,
  fetchSubscription,
  loginTrade,
  type BillingPlan,
  type SubscriptionState,
  type TradeSession,
} from '@/lib/subscribe-api'

/**
 * Subscribe — the web purchase surface the app points at ("Subscribe at
 * mytradeportal.co.uk", App Store 3.1.1 web-first billing).
 *
 * Views:
 * - login: email + password → POST /auth/token (bare-domain tenant resolution).
 * - plans: tiers from GET /billing/plans, monthly/yearly toggle (same pattern
 *   as the Pricing section). Subscribe → POST /billing/checkout → the
 *   returned checkout_url is this page with ?_ptxn=<txn> appended by Paddle
 *   (the transaction's checkout.url is our success_url), so the browser
 *   redirects back here into the checkout view.
 * - checkout: ?_ptxn present → Paddle.js opens the one-page overlay for the
 *   transaction. checkout.completed → done view; closed without paying →
 *   reopen affordance.
 * - done: /subscribe?done=1 (Paddle's success redirect target) or the
 *   completed event — "open the app and sign in".
 *
 * The session (bearer token + tenant id) lives in localStorage under
 * `mtp_subscribe_session`; the completed-transaction guard lives in
 * sessionStorage so a post-payment redirect carrying _ptxn again can't
 * re-open an already-completed checkout.
 */

type View = 'checkout' | 'done' | 'login' | 'plans'

type Interval = 'month' | 'year'

const SESSION_KEY = 'mtp_subscribe_session'
const completedKey = (txn: string) => `mtp_subscribe_completed_${txn}`

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
    // storage disabled — the session just won't survive a reload
  }
}

const PLAN_KEY_ALIASES: Record<string, string> = {
  starter: 'sole_trader',
  pro: 'pro',
  business: 'team',
}

const resolvePlanKey = (key: string) => PLAN_KEY_ALIASES[key] ?? key

const STATUS_LABELS: Record<string, string> = {
  trialing: 'Free trial',
  active: 'Active',
  past_due: 'Payment issue',
}

export function SubscribePanel() {
  usePageMeta(
    'Subscribe — My Trade Portal',
    'Pick a plan and subscribe to My Trade Portal. Your plan unlocks in the app automatically.',
  )

  const [searchParams] = useSearchParams()
  const checkoutTxn = searchParams.get('_ptxn')
  const doneParam = searchParams.get('done') === '1'
  const planParam = searchParams.get('plan')

  const [view, setView] = useState<View>(() => {
    if (checkoutTxn) {
      try {
        if (window.sessionStorage.getItem(completedKey(checkoutTxn))) return 'done'
      } catch {
        // sessionStorage unavailable — fall through and try to open checkout
      }
      return 'checkout'
    }
    if (doneParam) return 'done'
    return loadSession() ? 'plans' : 'login'
  })
  const [session, setSession] = useState<TradeSession | null>(() => loadSession())
  const [interval, setInterval] = useState<Interval>(() =>
    searchParams.get('interval') === 'year' ? 'year' : 'month',
  )

  const signIn = (next: TradeSession) => {
    saveSession(next)
    setSession(next)
    setView('plans')
  }

  const signOut = () => {
    saveSession(null)
    setSession(null)
    setView('login')
  }

  return (
    <section className="w-full max-w-[1100px]">
      {view === 'checkout' && checkoutTxn && (
        <CheckoutView
          txn={checkoutTxn}
          onCompleted={() => {
            try {
              window.sessionStorage.setItem(completedKey(checkoutTxn), '1')
            } catch {
              // best-effort guard only
            }
            window.history.replaceState(null, '', '/subscribe?done=1')
            setView('done')
          }}
        />
      )}
      {view === 'done' && <DoneView email={session?.email} />}
      {view === 'login' && <LoginView onSignedIn={signIn} />}
      {view === 'plans' && session && (
        <PlansView
          session={session}
          interval={interval}
          onIntervalChange={setInterval}
          selectedPlan={planParam ? resolvePlanKey(planParam) : null}
          onSessionExpired={signOut}
          onSignOut={signOut}
        />
      )}
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Login                                                               */
/* ------------------------------------------------------------------ */

function LoginView({ onSignedIn }: { onSignedIn: (session: TradeSession) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = email.trim().length > 0 && password.length > 0 && !submitting

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      onSignedIn(await loginTrade(email.trim(), password))
    } catch (err) {
      setError(
        err instanceof SubscribeApiError
          ? err.message
          : 'Something went wrong — please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Subscribe</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Sign in to subscribe
      </h1>
      <p className="mt-[var(--space-sm)] text-[14px] leading-relaxed text-[var(--muted)]">
        Use the email and password you registered with in the My Trade Portal app.
      </p>

      <form onSubmit={onSubmit} className="mt-[var(--space-lg)] space-y-[var(--space-md)]">
        <div>
          <label htmlFor="subscribe-email" className="spec-label text-[var(--muted)]">
            Email
          </label>
          <input
            id="subscribe-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
          />
        </div>

        <div>
          <label htmlFor="subscribe-password" className="spec-label text-[var(--muted)]">
            Password
          </label>
          <input
            id="subscribe-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
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

        <p className="text-[13px] leading-relaxed text-[var(--muted)]">
          Forgotten your password? Reset it from the app&apos;s sign-in screen first, then come
          back here.{' '}
          <Link to="/" className="link-arrow">
            Back home
          </Link>
        </p>
      </form>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Plan selection                                                      */
/* ------------------------------------------------------------------ */

function PlansView({
  session,
  interval,
  onIntervalChange,
  selectedPlan,
  onSessionExpired,
  onSignOut,
}: {
  session: TradeSession
  interval: Interval
  onIntervalChange: (interval: Interval) => void
  selectedPlan: string | null
  onSessionExpired: () => void
  onSignOut: () => void
}) {
  const [plans, setPlans] = useState<BillingPlan[] | null>(null)
  const [subscription, setSubscription] = useState<SubscriptionState | null>(null)
  const [loadError, setLoadError] = useState('')
  const [checkoutError, setCheckoutError] = useState('')
  const [busyPlan, setBusyPlan] = useState<string | null>(null)
  const [managing, setManaging] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([fetchBillingPlans(), fetchSubscription(session)])
      .then(([planList, sub]) => {
        if (cancelled) return
        setPlans(planList)
        setSubscription(sub)
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof SubscribeApiError && err.status === 401) {
          onSessionExpired()
          return
        }
        setLoadError('Couldn’t load the plans — check your connection and try again.')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.accessToken])

  const copyByKey = useMemo(() => new Map<string, (typeof PricingTiers)[number]>(PricingTiers.map((t) => [t.id, t])), [])

  const activeSubscription =
    subscription && ACTIVE_SUBSCRIPTION_STATUSES.has(subscription.status) ? subscription : null

  const subscribe = async (planKey: string) => {
    setBusyPlan(planKey)
    setCheckoutError('')
    try {
      // This page doubles as the Paddle checkout host: Paddle appends
      // ?_ptxn=<txn> to the transaction's checkout.url, so the browser comes
      // straight back here and the checkout view opens the overlay. The
      // ?done=1 marks the success redirect target.
      const successUrl = `${window.location.origin}/subscribe?done=1`
      const checkout = await createCheckout(session, planKey, interval, successUrl)
      window.location.assign(checkout.checkout_url)
    } catch (err) {
      setCheckoutError(
        err instanceof SubscribeApiError
          ? err.message
          : 'Checkout couldn’t be started — please try again.',
      )
      setBusyPlan(null)
    }
  }

  const manage = async () => {
    setManaging(true)
    setCheckoutError('')
    try {
      const { portal_url } = await createPortalSession(session)
      window.open(portal_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      setCheckoutError(
        err instanceof SubscribeApiError
          ? err.message
          : 'Couldn’t open subscription management — please try again.',
      )
    } finally {
      setManaging(false)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-[var(--space-md)]">
        <div>
          <p className="spec-label text-[var(--muted)]">Subscribe</p>
          <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.5rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            Pick your plan
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

        {!activeSubscription && (
          <div
            role="group"
            aria-label="Billing frequency"
            className="flex w-fit border-[1.5px] border-[var(--ink)]"
          >
            {(['month', 'year'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={interval === value}
                onClick={() => onIntervalChange(value)}
                className={`px-5 py-2.5 font-display text-[12px] font-bold uppercase tracking-[0.12em] transition-colors duration-[length:var(--dur-micro)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] ${
                  interval === value
                    ? 'bg-[var(--ink)] text-[var(--paper)]'
                    : 'text-[var(--muted)] hover:text-[var(--ink)]'
                }`}
              >
                {value === 'month' ? 'Monthly' : 'Yearly'}
              </button>
            ))}
          </div>
        )}
      </div>

      {loadError && (
        <p
          role="alert"
          className="mt-[var(--space-lg)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
        >
          {loadError}
        </p>
      )}

      {!plans && !loadError && (
        <div className="mt-[var(--space-xl)] flex items-center gap-3" role="status">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
          <p className="text-[14px] text-[var(--muted)]">Loading plans…</p>
        </div>
      )}

      {plans && activeSubscription && (
        <div className="mt-[var(--space-lg)] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-8">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-[clamp(1.2rem,2vw,1.6rem)] font-bold tracking-[0.01em]">
              You’re on the{' '}
              {plans.find((p) => p.key === resolvePlanKey(activeSubscription.plan_key))?.name ??
                resolvePlanKey(activeSubscription.plan_key)}{' '}
              plan
            </h2>
            <span className="border-[1.5px] border-[var(--ink)] bg-[var(--accent)] px-2.5 py-1 font-display text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--ink-deep)]">
              {STATUS_LABELS[activeSubscription.status] ?? activeSubscription.status}
            </span>
          </div>
          <p className="mt-[var(--space-sm)] max-w-[60ch] text-[14px] leading-relaxed text-[var(--muted)]">
            {activeSubscription.status === 'trialing' && activeSubscription.trial_ends_at
              ? `Your trial runs until ${new Date(activeSubscription.trial_ends_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}. `
              : ''}
            {activeSubscription.status === 'past_due'
              ? 'Your last payment failed — update your payment method to keep access. '
              : ''}
            {activeSubscription.seats} {activeSubscription.seats === 1 ? 'user' : 'users'} included
            ({activeSubscription.seats_in_use} in use). Your plan is already active in the app —
            manage payment method, invoices or cancellation via Paddle.
          </p>
          <div className="mt-[var(--space-md)] flex flex-wrap items-center gap-[var(--space-md)]">
            <button
              type="button"
              onClick={manage}
              disabled={managing}
              className="chip chip--fill disabled:cursor-not-allowed disabled:opacity-40"
            >
              {managing ? 'Opening…' : 'Manage subscription'}
            </button>
            {checkoutError && (
              <p role="alert" className="text-[13.5px] text-[var(--accent-dark)]">
                {checkoutError}
              </p>
            )}
          </div>
        </div>
      )}

      {plans && !activeSubscription && (
        <>
          {subscription?.status === 'incomplete' && (
            <p className="mt-[var(--space-md)] border-[1.5px] border-[var(--rule)] bg-[var(--paper-2)] px-4 py-3 text-[13.5px] leading-relaxed text-[var(--muted)]">
              Your previous checkout wasn’t completed — pick a plan below to start a fresh one.
            </p>
          )}

          {checkoutError && (
            <p
              role="alert"
              className="mt-[var(--space-md)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
            >
              {checkoutError}
            </p>
          )}

          <div className="mt-[var(--space-lg)] grid gap-[var(--space-md)] lg:grid-cols-3">
            {plans.map((plan) => {
              const copy = copyByKey.get(plan.key)
              const featured = plan.featured
              const isSelected = selectedPlan === plan.key
              const price = interval === 'year' ? plan.annual_price_gbp : plan.monthly_price_gbp
              return (
                <div
                  key={plan.key}
                  className={`relative flex flex-col p-[var(--space-lg)] md:p-[var(--space-xl)] ${
                    featured
                      ? 'bg-[var(--ink)] text-[var(--paper-on-dark)]'
                      : 'border-[1.5px] border-[var(--ink)] bg-[var(--paper)]'
                  } ${isSelected && !featured ? 'outline outline-2 outline-offset-2 outline-[var(--accent-dark)]' : ''}`}
                >
                  {featured && (
                    <span className="absolute right-0 top-0 bg-[var(--accent)] px-3 py-1.5 font-display text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--ink-deep)]">
                      Most popular
                    </span>
                  )}
                  <h3 className="font-display text-[clamp(1.3rem,1.9vw,1.75rem)] font-bold tracking-[0.01em]">
                    {plan.name}
                  </h3>
                  <p
                    className={`mt-1 text-[13.5px] ${featured ? 'text-[var(--paper-on-dark-muted)]' : 'text-[var(--muted)]'}`}
                  >
                    {copy?.tagline ?? ''}
                  </p>
                  <p className="tnum mt-[var(--space-lg)] flex items-end gap-2">
                    <span className="font-display text-[clamp(2.8rem,4vw,3.75rem)] font-extrabold leading-none tracking-[-0.02em]">
                      £{price}
                    </span>
                    <span
                      className={`pb-1.5 text-[13px] font-medium ${featured ? 'text-[var(--paper-on-dark-muted)]' : 'text-[var(--muted)]'}`}
                    >
                      per business /{interval === 'year' ? 'yr' : 'mo'}
                    </span>
                  </p>
                  <p
                    className={`spec-label mt-[var(--space-xs)] ${featured ? 'text-[var(--accent)]' : 'text-[var(--accent-dark)]'}`}
                  >
                    {copy?.audience ?? `${plan.seats} ${plan.seats === 1 ? 'user' : 'users'}`}
                  </p>
                  {copy && (
                    <ul
                      className={`mt-[var(--space-lg)] flex-1 space-y-[var(--space-sm)] border-t pt-[var(--space-lg)] text-[14px] ${
                        featured ? 'border-[var(--rule-on-dark)]' : 'border-[var(--rule)]'
                      }`}
                    >
                      {copy.features.map((f) => (
                        <li key={f} className="flex gap-[var(--space-sm)]">
                          <svg
                            viewBox="0 0 16 16"
                            className={`mt-1 h-3.5 w-3.5 shrink-0 ${featured ? 'text-[var(--accent)]' : 'text-[var(--accent-dark)]'}`}
                            fill="none"
                            aria-hidden
                          >
                            <path
                              d="m2.5 8.5 3.5 3.5 7.5-8"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="square"
                            />
                          </svg>
                          <span className={featured ? 'text-[var(--paper-on-dark)]' : 'text-[var(--ink)]'}>
                            {f}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <button
                    type="button"
                    onClick={() => subscribe(plan.key)}
                    disabled={busyPlan !== null}
                    className={`chip mt-[var(--space-xl)] justify-center disabled:cursor-not-allowed disabled:opacity-40 ${
                      featured ? 'chip--accent' : 'chip--fill'
                    }`}
                  >
                    {busyPlan === plan.key ? 'Starting checkout…' : `Subscribe — £${price}`}
                  </button>
                </div>
              )
            })}
          </div>

          <p className="mt-[var(--space-md)] text-[12.5px] leading-[1.7] text-[var(--muted)]">
            Every plan starts with a {plans[0]?.trial_days ?? 14}-day free trial — full features.
            Payment is handled securely by Paddle. AI is unmetered on every plan, subject to a
            generous{' '}
            <Link to="/fair-use" className="link-arrow">
              fair-use policy
            </Link>
            .
          </p>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Paddle checkout host (?_ptxn=…)                                     */
/* ------------------------------------------------------------------ */

function CheckoutView({ txn, onCompleted }: { txn: string; onCompleted: () => void }) {
  const [error, setError] = useState('')
  const [paddle, setPaddle] = useState<Paddle | undefined>()
  const [closed, setClosed] = useState(false)

  const token = import.meta.env.VITE_PADDLE_CLIENT_TOKEN as string | undefined

  useEffect(() => {
    if (!token) {
      setError('Checkout isn’t configured on this site yet — please try again later.')
      return
    }
    let cancelled = false
    initializePaddle({
      token,
      ...(import.meta.env.VITE_PADDLE_ENV
        ? { environment: import.meta.env.VITE_PADDLE_ENV as Environments }
        : {}),
      eventCallback: (event: { name?: string }) => {
        if (event.name === 'checkout.completed') {
          onCompleted()
        } else if (event.name === 'checkout.closed') {
          setClosed(true)
        } else if (event.name === 'checkout.error') {
          setError('Checkout couldn’t load — please try again.')
        }
      },
    }).then((p) => {
      if (!cancelled && p) setPaddle(p)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [txn])

  useEffect(() => {
    if (!paddle || error) return
    paddle.Checkout.open({ transactionId: txn, settings: { variant: 'one-page' } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paddle, txn])

  return (
    <div className="mx-auto w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Subscribe</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Secure checkout
      </h1>

      {error ? (
        <div className="mt-[var(--space-lg)]" role="alert">
          <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
            {error}
          </p>
          <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
            <Link to="/subscribe" className="link-arrow">
              Back to plans
            </Link>
          </p>
        </div>
      ) : (
        <div className="mt-[var(--space-lg)]">
          <div className="flex items-center gap-3" role="status">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
            <p className="text-[14px] text-[var(--muted)]">
              {closed
                ? 'Checkout closed — reopen it below whenever you’re ready.'
                : 'Opening secure checkout…'}
            </p>
          </div>
          <p className="mt-[var(--space-sm)] text-[13px] text-[var(--muted)]">
            Payment is processed by Paddle. Don’t close this tab while checkout is open.
          </p>
          {closed && (
            <button
              type="button"
              onClick={() => {
                setClosed(false)
                paddle?.Checkout.open({ transactionId: txn, settings: { variant: 'one-page' } })
              }}
              className="chip chip--fill mt-[var(--space-md)] w-full justify-center"
            >
              Reopen checkout
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Done                                                                */
/* ------------------------------------------------------------------ */

function DoneView({ email }: { email?: string }) {
  return (
    <div className="mx-auto w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Subscribe</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        You’re subscribed
      </h1>
      <div className="mt-[var(--space-lg)]" role="status">
        <p className="border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
          Your plan is active — it can take a few seconds to reach the app.
        </p>
        <p className="mt-[var(--space-md)] text-[14.5px] leading-relaxed">
          Open the My Trade Portal app and sign in{email ? ` with ${email}` : ''} — your
          subscription unlocks automatically.
        </p>
        {testflightConfigured() && (
          <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
            Don’t have the app yet?{' '}
            <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="link-arrow">
              Get it on TestFlight
            </a>
          </p>
        )}
        <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
          <Link to="/subscribe" className="link-arrow">
            Manage your subscription
          </Link>
        </p>
      </div>
    </div>
  )
}
