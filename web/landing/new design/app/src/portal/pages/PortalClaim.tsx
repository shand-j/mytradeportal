import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Eye, EyeOff } from 'lucide-react'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { usePageMeta } from '../../hooks/usePageMeta'
import { claimAccount, requestMagicLink, PortalApiError } from '../api'
import { APP_STORE_URL } from '../config'
import { saveSession } from '../session'

type Status = 'ready' | 'submitting' | 'success' | 'invalid' | 'sending' | 'sent'

const MIN_PASSWORD_LENGTH = 8

/** Light strength hint — "Good" (the minimum) is enough to submit. */
function passwordStrength(password: string): 'Good' | 'Strong' | null {
  if (password.length < MIN_PASSWORD_LENGTH) return null
  const hasVariety = /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password)
  return password.length >= 12 || hasVariety ? 'Strong' : 'Good'
}

/**
 * /claim — one-shot account-claim link from the booking-confirmation email
 * (?token=…&next=/quotes). The customer sets a password, we exchange the
 * token for a portal session (same storage as the magic-link flow) and show
 * a thank-you screen with the app-store link. Invalid/expired/used tokens
 * land on the "email me a new one" resend state.
 */
export default function PortalClaim() {
  const { slug, config } = usePortal()
  usePageMeta(
    `Create your account — ${config.name}`,
    `Create your ${config.name} customer portal account.`,
  )
  const [searchParams] = useSearchParams()
  const [token] = useState(() => searchParams.get('token') ?? '')
  const [status, setStatus] = useState<Status>(() => (token ? 'ready' : 'invalid'))
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState('')
  const [customerName, setCustomerName] = useState('')
  const [email, setEmail] = useState(searchParams.get('email') ?? '')

  const next = (() => {
    const target = searchParams.get('next') ?? '/quotes'
    // Only allow same-origin paths — never an open redirect.
    return target.startsWith('/') && !target.startsWith('//') ? target : '/quotes'
  })()

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const passwordsMismatch = confirm.length > 0 && password !== confirm
  const strength = passwordStrength(password)
  const canSubmit =
    status === 'ready' && password.length >= MIN_PASSWORD_LENGTH && password === confirm

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setStatus('submitting')
    setError('')
    try {
      const res = await claimAccount(token, password)
      saveSession(slug, {
        accessToken: res.access_token,
        expiresAt: res.expires_at,
        customer: res.customer,
      })
      setCustomerName(res.customer.full_name)
      setStatus('success')
      // Drop the single-use token from the URL so it doesn't linger in history.
      window.history.replaceState(null, '', window.location.pathname)
    } catch (err) {
      if (err instanceof PortalApiError && err.status === 401) {
        setStatus('invalid')
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
        setStatus('ready')
      }
    }
  }

  async function handleResend(e: React.FormEvent) {
    e.preventDefault()
    if (!email || status === 'sending') return
    setStatus('sending')
    try {
      await requestMagicLink(email)
    } finally {
      setStatus('sent')
    }
  }

  const passwordToggle = (show: boolean, setShow: (v: boolean) => void, label: string) => (
    <button
      type="button"
      onClick={() => setShow(!show)}
      aria-label={label}
      className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[var(--muted)] hover:text-[var(--ink)]"
    >
      {show ? <EyeOff size={18} /> : <Eye size={18} />}
    </button>
  )

  return (
    <PortalShell maxWidth="520px">
      <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
        {(status === 'ready' || status === 'submitting') && (
          <>
            <p className="spec-label text-[var(--muted)]">Welcome</p>
            <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
              Create your account
            </h1>
            <p className="mt-[var(--space-sm)] text-[14.5px] leading-relaxed text-[var(--muted)]">
              Choose a password to finish setting up your {config.name} customer portal account.
            </p>

            <form onSubmit={handleSubmit} className="mt-[var(--space-lg)] space-y-[var(--space-md)]">
              <div>
                <label htmlFor="claim-password" className="spec-label text-[var(--muted)]">
                  New password
                </label>
                <div className="relative mt-[var(--space-2xs)]">
                  <input
                    id="claim-password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    minLength={MIN_PASSWORD_LENGTH}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 pr-10 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
                  />
                  {passwordToggle(showPassword, setShowPassword, 'Show password')}
                </div>
                {passwordTooShort && (
                  <p className="mt-[var(--space-2xs)] text-[12.5px] text-[var(--accent-dark)]">
                    At least {MIN_PASSWORD_LENGTH} characters.
                  </p>
                )}
                {strength && (
                  <p className="mt-[var(--space-2xs)] text-[12.5px] font-semibold text-[var(--muted)]">
                    Strength: {strength}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="claim-confirm" className="spec-label text-[var(--muted)]">
                  Confirm password
                </label>
                <div className="relative mt-[var(--space-2xs)]">
                  <input
                    id="claim-confirm"
                    type={showConfirm ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 pr-10 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
                  />
                  {passwordToggle(showConfirm, setShowConfirm, 'Show confirm password')}
                </div>
                {passwordsMismatch && (
                  <p className="mt-[var(--space-2xs)] text-[12.5px] text-[var(--accent-dark)]">
                    Passwords don’t match.
                  </p>
                )}
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
                {status === 'submitting' ? 'Creating your account…' : 'Create account'}
              </button>
            </form>
          </>
        )}

        {status === 'success' && (
          <div role="status">
            <p className="spec-label text-[var(--muted)]">All set</p>
            <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
              Your account is ready
            </h1>
            <p className="mt-[var(--space-sm)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
              Welcome{customerName ? `, ${customerName}` : ''} — you’re signed in to your{' '}
              {config.name} customer portal.
            </p>
            <ul className="mt-[var(--space-md)] list-disc space-y-1 pl-5 text-[14.5px] leading-relaxed">
              <li>Track your quotes and approve them online</li>
              <li>See and manage your bookings</li>
              <li>Pay invoices securely</li>
              <li>Chat with {config.name}</li>
            </ul>
            <a
              href={APP_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="chip chip--fill mt-[var(--space-lg)] w-full justify-center"
            >
              Get the app
            </a>
            <p className="mt-[var(--space-md)] text-center text-[13.5px] text-[var(--muted)]">
              <Link to={next} className="link-arrow">
                Continue to your quotes
              </Link>
            </p>
          </div>
        )}

        {status === 'sent' ? (
          <div role="status">
            <p className="spec-label text-[var(--muted)]">Secure sign-in</p>
            <p className="mt-[var(--space-lg)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
              Check your inbox — we've emailed you a new sign-in link.
            </p>
          </div>
        ) : (
          (status === 'invalid' || status === 'sending') && (
            <div>
              <p className="spec-label text-[var(--muted)]">Secure sign-in</p>
              <div className="mt-[var(--space-lg)]">
                <p
                  className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
                  role="alert"
                >
                  This link has expired or has already been used. Account links are single-use —
                  we'll email you a fresh sign-in link instead.
                </p>
                <form
                  onSubmit={handleResend}
                  className="mt-[var(--space-md)] space-y-[var(--space-sm)]"
                >
                  <label htmlFor="claim-email" className="spec-label text-[var(--muted)]">
                    Your email
                  </label>
                  <input
                    id="claim-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={status === 'sending'}
                    className="chip chip--fill w-full justify-center disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {status === 'sending' ? 'Sending…' : 'Email me a new one'}
                  </button>
                </form>
              </div>
            </div>
          )
        )}
      </section>
    </PortalShell>
  )
}
