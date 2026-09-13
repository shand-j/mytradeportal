import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { RequireAuth } from '../components/auth'
import { usePageMeta } from '../../hooks/usePageMeta'
import { listQuotes, SessionExpiredError, type CustomerQuote } from '../api'
import { DocumentLoading, formatDate, formatMoney, StatusBadge } from '../../pages/ViewQuote'

function QuotesList() {
  const { slug, sessionVersion } = usePortal()
  const [status, setStatus] = useState<'loading' | 'error' | 'loaded'>('loading')
  const [error, setError] = useState('')
  const [quotes, setQuotes] = useState<CustomerQuote[]>([])

  useEffect(() => {
    let cancelled = false
    listQuotes(slug)
      .then((data) => {
        if (cancelled) return
        setQuotes(data)
        setStatus('loaded')
      })
      .catch((err) => {
        if (cancelled || err instanceof SessionExpiredError) return
        setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [slug, sessionVersion])

  if (status === 'loading') return <DocumentLoading label="Loading your quotes…" />
  if (status === 'error') {
    return (
      <p role="alert" className="mt-[var(--space-lg)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        {error}
      </p>
    )
  }
  if (quotes.length === 0) {
    return (
      <p className="mt-[var(--space-lg)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5 text-[14px] leading-relaxed text-[var(--muted)]">
        No quotes yet. When {`you've`} requested work, your quotes will show up here.
      </p>
    )
  }
  return (
    <ul className="mt-[var(--space-lg)] space-y-3">
      {quotes.map((quote) => (
        <li key={quote.id}>
          <Link
            to={`/quotes/${quote.id}`}
            className="flex flex-wrap items-center gap-3 border-2 border-[var(--ink)] bg-[var(--paper)] px-4 py-3.5 transition-colors hover:bg-[var(--paper-2)]"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-bold">{quote.title}</p>
              <p className="text-[12.5px] text-[var(--muted)]">
                {quote.sent_at ? `Sent ${formatDate(quote.sent_at)}` : `Created ${formatDate(quote.created_at)}`}
              </p>
            </div>
            <p className="text-[15px] font-extrabold">{formatMoney('GBP', quote.total)}</p>
            <StatusBadge status={quote.status} />
          </Link>
        </li>
      ))}
    </ul>
  )
}

export default function PortalQuotes() {
  const { config } = usePortal()
  usePageMeta(`Your quotes — ${config.name}`, `Quotes from ${config.name}.`)
  return (
    <PortalShell>
      <p className="spec-label text-[var(--muted)]">Your quotes</p>
      <h1 className="mt-[var(--space-2xs)] font-display text-[clamp(1.4rem,3.5vw,2rem)] font-extrabold uppercase tracking-[0.02em]">
        Quotes
      </h1>
      <RequireAuth>
        <QuotesList />
      </RequireAuth>
    </PortalShell>
  )
}
