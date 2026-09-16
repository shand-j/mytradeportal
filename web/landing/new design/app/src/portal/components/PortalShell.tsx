import { useState } from 'react'
import { Link } from 'react-router'
import { usePortal } from '../context'
import { getSession } from '../session'
import { requestMagicLink } from '../api'

/**
 * Global session-expired banner: "Your session has expired — email me a new
 * link". Uses the stored customer email when we still have it, otherwise
 * asks for it.
 */
function SessionExpiredBanner() {
  const { slug, dismissSessionExpired } = usePortal()
  const knownEmail = getSession(slug)?.customer.email ?? ''
  const [email, setEmail] = useState(knownEmail)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  async function handleSend(e: React.FormEvent) {
    e.preventDefault()
    if (!email || sending) return
    setSending(true)
    try {
      await requestMagicLink(email, slug)
      setSent(true)
    } finally {
      setSending(false)
    }
  }

  return (
    <div role="alert" className="border-b-2 border-[var(--ink)] bg-[var(--accent)] px-5 py-3">
      <div className="mx-auto flex w-full max-w-[720px] flex-wrap items-center gap-3">
        {sent ? (
          <p className="text-[13.5px] font-semibold leading-relaxed text-[var(--ink-deep)]">
            Check your inbox — we've emailed you a new sign-in link.
          </p>
        ) : (
          <>
            <p className="text-[13.5px] font-semibold leading-relaxed text-[var(--ink-deep)]">
              Your session has expired.
            </p>
            <form onSubmit={handleSend} className="flex flex-1 flex-wrap items-center gap-2">
              {!knownEmail && (
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="min-w-[180px] flex-1 border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-1.5 text-[13.5px] focus:outline-none"
                />
              )}
              <button
                type="submit"
                disabled={sending}
                className="border-2 border-[var(--ink)] bg-[var(--ink)] px-3 py-1.5 text-[12.5px] font-bold uppercase tracking-[0.06em] text-[var(--paper)] disabled:opacity-50"
              >
                {sending ? 'Sending…' : 'Email me a new link'}
              </button>
            </form>
          </>
        )}
        <button
          type="button"
          onClick={dismissSessionExpired}
          aria-label="Dismiss"
          className="ml-auto text-[18px] font-bold leading-none text-[var(--ink-deep)]"
        >
          ×
        </button>
      </div>
    </div>
  )
}

/**
 * Portal chrome — tenant-branded header/footer replacing the marketing
 * Nav/Footer in portal mode. Mobile-first: customers arrive from email on
 * phones.
 */
export function PortalShell({
  children,
  maxWidth = '720px',
}: {
  children: React.ReactNode
  maxWidth?: string
}) {
  const { config, sessionExpired } = usePortal()
  return (
    <main className="relative flex min-h-screen flex-col">
      {sessionExpired && <SessionExpiredBanner />}
      <header
        className="border-b-2 border-[var(--ink)]"
        style={{ backgroundColor: config.primary_color || '#0F1E26' }}
      >
        <div className="mx-auto flex w-full max-w-[720px] items-center gap-3 px-5 py-4">
          {config.logo_url && (
            <img
              src={config.logo_url}
              alt={`${config.name} logo`}
              className="h-10 w-10 border-2 border-white/40 bg-white object-contain"
            />
          )}
          <div className="min-w-0 flex-1">
            <Link
              to="/"
              className="block truncate font-display text-[17px] font-extrabold uppercase tracking-[0.02em] text-white"
            >
              {config.name}
            </Link>
            <p className="text-[11px] uppercase tracking-[0.1em] text-white/75">Customer portal</p>
          </div>
          <nav className="flex items-center gap-4 text-[12px] font-bold uppercase tracking-[0.06em] text-white">
            <Link to="/quotes" className="underline-offset-2 hover:underline">
              Quotes
            </Link>
            <Link to="/invoices" className="underline-offset-2 hover:underline">
              Invoices
            </Link>
            {config.phone && (
              <a href={`tel:${config.phone}`} className="underline-offset-2 hover:underline">
                Call
              </a>
            )}
          </nav>
        </div>
      </header>

      <div className="flex flex-1 justify-center px-5 py-[var(--space-xl)]">
        <div className="w-full" style={{ maxWidth }}>
          {children}
        </div>
      </div>

      <footer className="border-t-2 border-[var(--ink)] bg-[var(--paper-2)] px-5 py-4">
        <div className="mx-auto w-full max-w-[720px]">
          <p className="text-[12.5px] text-[var(--muted)]">
            Powered by{' '}
            <a
              href="https://mytradeportal.co.uk"
              className="font-semibold text-[var(--ink)] underline underline-offset-2"
            >
              My Trade Portal
            </a>
          </p>
        </div>
      </footer>
    </main>
  )
}
