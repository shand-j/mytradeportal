import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { RequireAuth } from '../components/auth'
import { usePageMeta } from '../../hooks/usePageMeta'
import { listInvoices, SessionExpiredError, type CustomerInvoice } from '../api'
import { DocumentLoading, formatDate, formatMoney, StatusBadge } from '../../pages/ViewQuote'

function InvoicesList() {
  const { slug, sessionVersion } = usePortal()
  const [status, setStatus] = useState<'loading' | 'error' | 'loaded'>('loading')
  const [error, setError] = useState('')
  const [invoices, setInvoices] = useState<CustomerInvoice[]>([])

  useEffect(() => {
    let cancelled = false
    listInvoices(slug)
      .then((data) => {
        if (cancelled) return
        setInvoices(data)
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

  if (status === 'loading') return <DocumentLoading label="Loading your invoices…" />
  if (status === 'error') {
    return (
      <p role="alert" className="mt-[var(--space-lg)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        {error}
      </p>
    )
  }
  if (invoices.length === 0) {
    return (
      <p className="mt-[var(--space-lg)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5 text-[14px] leading-relaxed text-[var(--muted)]">
        No invoices yet — they'll appear here once work has been billed.
      </p>
    )
  }
  return (
    <ul className="mt-[var(--space-lg)] space-y-3">
      {invoices.map((invoice) => (
        <li key={invoice.id}>
          <Link
            to={`/invoices/${invoice.id}`}
            className="flex flex-wrap items-center gap-3 border-2 border-[var(--ink)] bg-[var(--paper)] px-4 py-3.5 transition-colors hover:bg-[var(--paper-2)]"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-bold">Invoice {invoice.invoice_number}</p>
              <p className="text-[12.5px] text-[var(--muted)]">
                Issued {formatDate(invoice.issue_date)}
                {invoice.due_date && invoice.status !== 'paid' && (
                  <> · due {formatDate(invoice.due_date)}</>
                )}
              </p>
            </div>
            <p className="text-[15px] font-extrabold">{formatMoney('GBP', invoice.total)}</p>
            <StatusBadge status={invoice.status} />
          </Link>
        </li>
      ))}
    </ul>
  )
}

export default function PortalInvoices() {
  const { config } = usePortal()
  usePageMeta(`Your invoices — ${config.name}`, `Invoices from ${config.name}.`)
  return (
    <PortalShell>
      <p className="spec-label text-[var(--muted)]">Your invoices</p>
      <h1 className="mt-[var(--space-2xs)] font-display text-[clamp(1.4rem,3.5vw,2rem)] font-extrabold uppercase tracking-[0.02em]">
        Invoices
      </h1>
      <RequireAuth>
        <InvoicesList />
      </RequireAuth>
    </PortalShell>
  )
}
