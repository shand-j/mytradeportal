import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { usePageMeta } from '../../hooks/usePageMeta'
import { consumeMagicToken, requestMagicLink } from '../api'
import { saveSession } from '../session'

type Status = 'consuming' | 'invalid' | 'sending' | 'sent'

/**
 * /auth/magic — consumes a magic-link token (?token=…&next=/quotes/{id}),
 * stores the portal session and redirects. Expired/invalid tokens land on a
 * "this link has expired — email me a new one" state.
 */
export default function PortalMagicAuth() {
  const { slug, config } = usePortal()
  usePageMeta(`Sign in — ${config.name}`, `Sign in to your ${config.name} customer portal.`)
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<Status>(() =>
    searchParams.get('token') ? 'consuming' : 'invalid',
  )
  const [email, setEmail] = useState(searchParams.get('email') ?? '')
  const startedRef = useRef(false)

  const next = (() => {
    const target = searchParams.get('next') ?? '/quotes'
    // Only allow same-origin paths — never an open redirect.
    return target.startsWith('/') && !target.startsWith('//') ? target : '/quotes'
  })()

  useEffect(() => {
    const token = searchParams.get('token')
    if (!token || startedRef.current) return
    startedRef.current = true
    consumeMagicToken(token)
      .then((res) => {
        saveSession(slug, {
          accessToken: res.access_token,
          expiresAt: res.expires_at,
          customer: res.customer,
        })
        navigate(next, { replace: true })
      })
      .catch(() => setStatus('invalid'))
  }, [searchParams, slug, navigate, next])

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

  return (
    <PortalShell maxWidth="520px">
      <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
        <p className="spec-label text-[var(--muted)]">Secure sign-in</p>
        {status === 'consuming' && (
          <div className="mt-[var(--space-lg)] flex items-center gap-3" role="status">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
            <p className="text-[14px] text-[var(--muted)]">Signing you in…</p>
          </div>
        )}

        {status === 'sent' ? (
          <div className="mt-[var(--space-lg)]" role="status">
            <p className="border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
              Check your inbox — we've emailed you a new sign-in link.
            </p>
          </div>
        ) : (
          status !== 'consuming' && (
            <div className="mt-[var(--space-lg)]">
              <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed" role="alert">
                This link has expired or has already been used. Magic links are single-use — we'll
                email you a fresh one.
              </p>
              <form onSubmit={handleResend} className="mt-[var(--space-md)] space-y-[var(--space-sm)]">
                <label htmlFor="magic-email" className="spec-label text-[var(--muted)]">
                  Your email
                </label>
                <input
                  id="magic-email"
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
                  {status === 'sending' ? 'Sending…' : 'Email me a new link'}
                </button>
              </form>
            </div>
          )
        )}
      </section>
    </PortalShell>
  )
}
