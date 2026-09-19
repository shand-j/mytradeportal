import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { usePageMeta } from '../../hooks/usePageMeta'
import { acceptInvite } from '../../lib/invite-api'
import { TESTFLIGHT_URL, testflightConfigured } from '@/lib/site'

type Status = 'ready' | 'invalid' | 'submitting' | 'success'

const MIN_PASSWORD_LENGTH = 8

/**
 * Team-invite acceptance panel on the marketing /accept-invite page. Unlike
 * the reset flow there is no inspect step — the API confirms the account
 * email after the password is saved.
 */
export function AcceptInvitePanel() {
  usePageMeta(
    'Accept your invite — My Trade Portal',
    'Set a password to activate your My Trade Portal team account.',
  )

  const [searchParams] = useSearchParams()
  const [token] = useState(() => searchParams.get('token') ?? '')
  const [status, setStatus] = useState<Status>(() => (token ? 'ready' : 'invalid'))
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')

  const passwordTooShort = password.length > 0 && password.length < MIN_PASSWORD_LENGTH
  const passwordsMismatch = confirm.length > 0 && password !== confirm
  const canSubmit =
    status === 'ready' && password.length >= MIN_PASSWORD_LENGTH && password === confirm

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setStatus('submitting')
    setError('')
    try {
      const result = await acceptInvite(token, password)
      setEmail(result.email)
      setStatus('success')
      window.history.replaceState(null, '', window.location.pathname)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
      setStatus('ready')
    }
  }

  return (
    <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Team invite</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Set your password
      </h1>

      {status === 'invalid' && (
        <div className="mt-[var(--space-lg)]" role="alert">
          <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
            This invite link is invalid or has expired. Ask for a fresh one from the app’s
            login screen (“Been invited? Get your sign-in link”) or from the person who
            invited you.
          </p>
          <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
            <Link to="/" className="link-arrow">
              Back home
            </Link>
          </p>
        </div>
      )}

      {(status === 'ready' || status === 'submitting') && (
        <form onSubmit={onSubmit} className="mt-[var(--space-lg)] space-y-[var(--space-md)]">
          <p className="text-[14px] leading-relaxed text-[var(--muted)]">
            Choose a password to activate your account. You’ll log in to the app with your
            invited email address and this password.
          </p>

          <div>
            <label htmlFor="new-password" className="spec-label text-[var(--muted)]">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
            />
            {passwordTooShort && (
              <p className="mt-[var(--space-2xs)] text-[12.5px] text-[var(--accent-dark)]">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
          </div>

          <div>
            <label htmlFor="confirm-password" className="spec-label text-[var(--muted)]">
              Reconfirm new password
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
            />
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
            {status === 'submitting' ? 'Activating…' : 'Activate my account'}
          </button>
        </form>
      )}

      {status === 'success' && (
        <div className="mt-[var(--space-lg)]" role="status">
          <p className="border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
            Your account is ready — log in as {email}.
          </p>
          <p className="mt-[var(--space-md)] text-[14.5px] leading-relaxed">
            Open the My Trade Portal app and log in with this email address and your new
            password.
          </p>
          {testflightConfigured() && (
            <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
              Don’t have the app yet?{' '}
              <a
                href={TESTFLIGHT_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="link-arrow"
              >
                Get it on TestFlight
              </a>
            </p>
          )}
        </div>
      )}
    </section>
  )
}
