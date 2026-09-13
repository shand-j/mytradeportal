import { useEffect, useState, type ReactNode } from 'react'
import { fetchPublicConfig, PortalApiError, type PortalConfig } from './api'
import { onSessionExpired } from './session'
import { PortalContext } from './context'
import { useNoIndex } from '../pages/ViewQuote'
import PortalNotFound from './pages/PortalNotFound'

type ConfigStatus = 'loading' | 'ready' | 'not-found' | 'error'

function PortalLoading() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center px-5">
      <div className="flex items-center gap-3" role="status">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
        <p className="text-[14px] text-[var(--muted)]">Loading…</p>
      </div>
    </main>
  )
}

function PortalConfigError({ onRetry }: { onRetry: () => void }) {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center px-5">
      <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
        <p className="spec-label text-[var(--muted)]">Customer portal</p>
        <div className="mt-[var(--space-lg)]" role="alert">
          <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
            Something went wrong loading this page — please try again.
          </p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="chip chip--fill mt-[var(--space-lg)] justify-center"
        >
          Try again
        </button>
      </section>
    </main>
  )
}

/**
 * Portal-mode root: fetches the tenant's public config once, applies tenant
 * branding (the DocumentShell pattern — inline brand colours plus the
 * --accent CSS var), marks the portal noindex, and renders a friendly
 * not-found page (with a code-entry box) for unknown slugs.
 */
export function PortalProvider({ slug, children }: { slug: string; children: ReactNode }) {
  useNoIndex()
  const [status, setStatus] = useState<ConfigStatus>('loading')
  const [config, setConfig] = useState<PortalConfig | null>(null)
  const [retryCount, setRetryCount] = useState(0)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [sessionVersion, setSessionVersion] = useState(0)

  useEffect(
    () =>
      onSessionExpired(() => {
        setSessionExpired(true)
        setSessionVersion((v) => v + 1)
      }),
    [],
  )

  useEffect(() => {
    let cancelled = false
    fetchPublicConfig(slug)
      .then((cfg) => {
        if (cancelled) return
        setConfig(cfg)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus(err instanceof PortalApiError && err.status === 404 ? 'not-found' : 'error')
      })
    return () => {
      cancelled = true
    }
  }, [slug, retryCount])

  /* Tenant branding: the portal accent follows the business primary colour. */
  useEffect(() => {
    if (!config) return
    const root = document.documentElement
    const previous = root.style.getPropertyValue('--accent')
    root.style.setProperty('--accent', config.primary_color)
    const previousTitle = document.title
    document.title = `${config.name} — customer portal`
    return () => {
      root.style.setProperty('--accent', previous)
      document.title = previousTitle
    }
  }, [config])

  if (status === 'loading') return <PortalLoading />
  if (status === 'not-found') return <PortalNotFound slug={slug} />
  if (status === 'error' || !config) {
    return (
      <PortalConfigError
        onRetry={() => {
          setStatus('loading')
          setRetryCount((c) => c + 1)
        }}
      />
    )
  }

  return (
    <PortalContext.Provider
      value={{
        slug,
        config,
        sessionExpired,
        dismissSessionExpired: () => setSessionExpired(false),
        sessionVersion,
      }}
    >
      {children}
    </PortalContext.Provider>
  )
}
