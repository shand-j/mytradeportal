import { useState } from 'react'
import { usePortal } from '../context'
import { getSession } from '../session'
import { requestMagicLink } from '../api'

/**
 * Invisible-auth sign-in: the customer enters their email and gets a magic
 * link. Always ends at the same "check your inbox" state — the backend
 * answers 202 generic whether or not the address is known.
 */
export function SignInPanel({ heading = 'Sign in to continue' }: { heading?: string }) {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent'>('idle')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email || status === 'sending') return
    setStatus('sending')
    try {
      await requestMagicLink(email)
    } finally {
      setStatus('sent')
    }
  }

  if (status === 'sent') {
    return (
      <div className="border-2 border-[var(--ink)] bg-[var(--accent)] p-5" role="status">
        <p className="text-[14.5px] font-semibold leading-relaxed text-[var(--ink-deep)]">
          Check your inbox — if {email} has quotes or invoices with us, a sign-in link is on its
          way. The link works on this device and lasts a short while.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5">
      <p className="text-[14px] font-semibold leading-relaxed">{heading}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-[var(--muted)]">
        Enter the email address your electrician has for you — we'll send a secure sign-in link.
        No password needed.
      </p>
      <div className="mt-[var(--space-md)] flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="flex-1 border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
        />
        <button
          type="submit"
          disabled={status === 'sending'}
          className="chip chip--fill justify-center disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status === 'sending' ? 'Sending…' : 'Email me a link'}
        </button>
      </div>
    </form>
  )
}

/**
 * Auth gate for portal pages: renders children with a valid session,
 * otherwise the magic-link sign-in panel. Re-checks when the global
 * session-expired event fires (sessionVersion bump).
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { slug, sessionVersion } = usePortal()
  void sessionVersion // re-render trigger after session invalidation
  const session = getSession(slug)
  if (!session) {
    return (
      <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
        <SignInPanel />
      </section>
    )
  }
  return <>{children}</>
}
