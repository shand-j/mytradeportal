import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { usePageMeta } from '../../hooks/usePageMeta'
import { confirmPasswordReset, inspectResetToken } from '../../lib/reset-api'
import { TESTFLIGHT_URL, testflightConfigured } from '@/lib/site'

type Status = 'verifying' | 'invalid' | 'ready' | 'submitting' | 'success'

const MIN_PASSWORD_LENGTH = 8

/**
 * Password-reset panel shared by the marketing /reset-password page (Nav +
 * Footer chrome) and the portal-branded /reset-password route. Chrome is the
 * caller's job; this component owns the token verify + form flow.
 */
export function ResetPasswordPanel() {
  usePageMeta(
    'Reset your password — My Trade Portal',
    'Choose a new password for your My Trade Portal account.',
  )

  const [searchParams] = useSearchParams()
  const [token] = useState(() => searchParams.get('token') ?? '')
  const [status, setStatus] = useState<Status>(() =>
    searchParams.get('token') ? 'verifying' : 'invalid',
  )
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')

  /* Verify the token on load so we can show whose password is being reset.
     The token is then stripped from the URL so it doesn't linger in history. */
  useEffect(() => {
    if (!token) return
    let cancelled = false
    inspectResetToken(token)
      .then((info) => {
        if (cancelled) return
        setEmail(info.email)
        setStatus('ready')
        window.history.replaceState(null, '', window.location.pathname)
      })
      .catch(() => {
        if (!cancelled) setStatus('invalid')
      })
    return () => {
      cancelled = true
    }
  }, [token])

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
      await confirmPasswordReset(token, password)
      setStatus('success')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
      setStatus('ready')
    }
  }

  return (
    <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Account security</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Reset your password
      </h1>

      {status === 'verifying' && (
        <div className="mt-[var(--space-lg)] flex items-center gap-3" role="status">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
          <p className="text-[14px] text-[var(--muted)]">Checking your reset link…</p>
        </div>
      )}

      {status === 'invalid' && (
        <div className="mt-[var(--space-lg)]" role="alert">
          <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
            This reset link is invalid or has expired. Links are single-use and last 30 minutes —
            request a fresh one from the app’s forgotten-password screen.
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
          <div>
            <p className="spec-label text-[var(--muted)]">Account</p>
            <p className="mt-[var(--space-2xs)] border-2 border-[var(--rule)] bg-[var(--paper-2)] px-3.5 py-2.5 font-mono text-[14px]">
              {email}
            </p>
          </div>

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
            {status === 'submitting' ? 'Updating…' : 'Set new password'}
          </button>
        </form>
      )}

      {status === 'success' && (
        <div className="mt-[var(--space-lg)]" role="status">
          <p className="border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
            Password updated for {email}.
          </p>
          <p className="mt-[var(--space-md)] text-[14.5px] leading-relaxed">
            You can now return to the My Trade Portal app and log in with your new password.
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
