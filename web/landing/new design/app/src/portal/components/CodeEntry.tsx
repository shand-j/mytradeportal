import { useState } from 'react'
import { fetchPublicConfigByCode, PortalApiError } from '../api'
import { portalUrlForSlug } from '../host'

/**
 * 6-digit business-code redemption: resolves the code to a tenant slug via
 * the public by-code endpoint and bounces the visitor to that tenant's
 * subdomain with a full navigation (new host, fresh portal load).
 */
export function CodeEntry({ compact = false }: { compact?: boolean }) {
  const [code, setCode] = useState('')
  const [status, setStatus] = useState<'idle' | 'checking' | 'invalid'>('idle')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (code.length !== 6 || status === 'checking') return
    setStatus('checking')
    try {
      const config = await fetchPublicConfigByCode(code)
      window.location.assign(portalUrlForSlug(config.slug))
    } catch (err) {
      setStatus(err instanceof PortalApiError && err.status === 404 ? 'invalid' : 'idle')
      if (!(err instanceof PortalApiError)) setStatus('idle')
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      {!compact && (
        <label htmlFor="business-code" className="spec-label text-[var(--muted)]">
          Have a 6-digit code from your electrician?
        </label>
      )}
      <div className={`flex gap-2 ${compact ? '' : 'mt-[var(--space-2xs)]'}`}>
        <input
          id="business-code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          value={code}
          onChange={(e) => {
            setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
            setStatus('idle')
          }}
          placeholder="123456"
          aria-label="6-digit business code"
          className="w-32 border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-center font-mono text-[16px] tracking-[0.3em] focus:outline-none focus-visible:outline-2 focus-visible:outline-[var(--accent-dark)]"
        />
        <button
          type="submit"
          disabled={code.length !== 6 || status === 'checking'}
          className="chip chip--fill justify-center disabled:cursor-not-allowed disabled:opacity-40"
        >
          {status === 'checking' ? 'Checking…' : 'Go'}
        </button>
      </div>
      {status === 'invalid' && (
        <p role="alert" className="mt-[var(--space-2xs)] text-[12.5px] text-[var(--accent-dark)]">
          We don't recognise that code — check it with your electrician and try again.
        </p>
      )}
    </form>
  )
}
