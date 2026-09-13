import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import {
  fetchPublicDocument,
  PublicDocsApiError,
  type PublicDocPayload,
} from '../lib/public-docs-api'
import { TESTFLIGHT_URL, testflightConfigured } from '@/lib/site'
import { isPortalMode } from '../portal/host'

type Status = 'loading' | 'invalid' | 'error' | 'loaded'

/* Shared helpers — ViewInvoice reuses these so both documents render
   identically apart from their status-specific calls to action. */

export function useNoIndex(): void {
  useEffect(() => {
    let meta = document.querySelector<HTMLMetaElement>('meta[name="robots"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'robots'
      document.head.appendChild(meta)
    }
    meta.content = 'noindex, nofollow'
  }, [])
}

export function usePublicDocument(kind: 'quote' | 'invoice') {
  const { token = '' } = useParams()
  const [status, setStatus] = useState<Status>(token ? 'loading' : 'invalid')
  const [error, setError] = useState('')
  const [doc, setDoc] = useState<PublicDocPayload | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    fetchPublicDocument(kind, token)
      .then((payload) => {
        if (cancelled) return
        setDoc(payload)
        setStatus('loaded')
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof PublicDocsApiError && err.status === 404) {
          setStatus('invalid')
        } else {
          setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
          setStatus('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [kind, token])

  return { status, error, doc }
}

export function formatMoney(currency: string, value: string): string {
  const amount = Number(value)
  if (Number.isNaN(amount)) return value
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(amount)
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  sent: 'Awaiting response',
  approved: 'Accepted',
  rejected: 'Declined',
  invoiced: 'Invoiced',
  expired: 'Expired',
  paid: 'Paid',
  cancelled: 'Cancelled',
}

export function StatusBadge({ status }: { status: string }) {
  const positive = status === 'approved' || status === 'accepted' || status === 'paid'
  const negative = status === 'rejected' || status === 'cancelled'
  return (
    <span
      className="inline-block border-2 px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.08em]"
      style={{
        borderColor: positive ? '#15803d' : negative ? '#b91c1c' : 'var(--ink)',
        color: positive ? '#15803d' : negative ? '#b91c1c' : 'var(--ink)',
        backgroundColor: positive ? '#15803d14' : negative ? '#b91c1c14' : 'transparent',
      }}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

export function DocumentLoading({ label }: { label: string }) {
  return (
    <div className="mt-[var(--space-lg)] flex items-center gap-3" role="status">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
      <p className="text-[14px] text-[var(--muted)]">{label}</p>
    </div>
  )
}

export function DocumentInvalid({ kind }: { kind: 'quote' | 'invoice' }) {
  return (
    <div className="mt-[var(--space-lg)]" role="alert">
      <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        This {kind} link is invalid or has expired. Ask your electrician to send you a fresh one —
        the newest email always has the working link.
      </p>
      <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
        <Link to="/" className="link-arrow">
          Back to mytradeportal.co.uk
        </Link>
      </p>
    </div>
  )
}

export function DocumentError({ message }: { message: string }) {
  return (
    <div className="mt-[var(--space-lg)]" role="alert">
      <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        {message}
      </p>
    </div>
  )
}

export function DocumentShell({
  doc,
  heading,
  children,
}: {
  doc: PublicDocPayload
  heading: string
  children?: React.ReactNode
}) {
  const brand = doc.tenant.brand_color || '#0F1E26'
  const vatPercent = Math.round(Number(doc.vat_rate) * 100)
  return (
    <section className="w-full max-w-[720px] border-2 border-[var(--ink)] bg-[var(--paper)]">
      <header
        className="flex flex-wrap items-center gap-[var(--space-md)] border-b-2 border-[var(--ink)] px-6 py-5 md:px-10"
        style={{ backgroundColor: brand }}
      >
        {doc.tenant.logo_url && (
          <img
            src={doc.tenant.logo_url}
            alt={`${doc.tenant.name} logo`}
            className="h-10 w-10 border-2 border-white/40 bg-white object-contain"
          />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-[18px] font-extrabold uppercase tracking-[0.02em] text-white">
            {doc.tenant.name}
          </p>
          <p className="text-[12px] uppercase tracking-[0.1em] text-white/75">{heading}</p>
        </div>
        <StatusBadge status={doc.status} />
      </header>

      <div className="px-6 py-[var(--space-lg)] md:px-10">
        <p className="text-[14px] text-[var(--muted)]">Hi {doc.customer_first_name},</p>
        {doc.title && (
          <h1 className="mt-[var(--space-2xs)] font-display text-[clamp(1.4rem,3vw,1.9rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            {doc.title}
          </h1>
        )}
        {doc.description && (
          <p className="mt-[var(--space-sm)] whitespace-pre-line text-[14.5px] leading-relaxed text-[var(--ink)]">
            {doc.description}
          </p>
        )}
        <p className="mt-[var(--space-sm)] text-[13px] text-[var(--muted)]">
          {doc.kind === 'quote' && doc.valid_until && <>Valid until {formatDate(doc.valid_until)}</>}
          {doc.kind === 'invoice' && (doc.due_date || doc.paid_at) && (
            <>
              {doc.due_date && <>Due by {formatDate(doc.due_date)}</>}
              {doc.due_date && doc.paid_at && <> · </>}
              {doc.paid_at && <>Paid on {formatDate(doc.paid_at)}</>}
            </>
          )}
        </p>

        <table className="mt-[var(--space-lg)] w-full border-collapse text-[14px]">
          <thead>
            <tr className="border-b-2 border-[var(--ink)] text-left">
              <th className="py-2 pr-3 font-bold">Item</th>
              <th className="px-3 py-2 text-right font-bold">Qty</th>
              <th className="px-3 py-2 text-right font-bold">Unit price</th>
              <th className="py-2 pl-3 text-right font-bold">Total</th>
            </tr>
          </thead>
          <tbody>
            {doc.lines.map((line, i) => (
              <tr key={i} className="border-b border-[var(--rule)]">
                <td className="py-2.5 pr-3 align-top">{line.description}</td>
                <td className="px-3 py-2.5 text-right align-top whitespace-nowrap">
                  {Number(line.quantity)} {line.unit !== 'ea' ? line.unit : ''}
                </td>
                <td className="px-3 py-2.5 text-right align-top whitespace-nowrap">
                  {formatMoney(doc.currency, line.unit_price)}
                </td>
                <td className="py-2.5 pl-3 text-right align-top whitespace-nowrap">
                  {formatMoney(doc.currency, line.total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="ml-auto mt-[var(--space-md)] w-full max-w-[280px] text-[14px]">
          <div className="flex justify-between py-1">
            <dt className="text-[var(--muted)]">Subtotal (ex VAT)</dt>
            <dd>{formatMoney(doc.currency, doc.subtotal)}</dd>
          </div>
          <div className="flex justify-between border-b border-[var(--rule)] py-1">
            <dt className="text-[var(--muted)]">VAT{vatPercent ? ` (${vatPercent}%)` : ''}</dt>
            <dd>{formatMoney(doc.currency, doc.vat_amount)}</dd>
          </div>
          <div className="flex justify-between py-2 text-[16px] font-extrabold">
            <dt>Total</dt>
            <dd>{formatMoney(doc.currency, doc.total)}</dd>
          </div>
        </dl>

        {children}
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-[var(--space-sm)] border-t-2 border-[var(--ink)] bg-[var(--paper-2)] px-6 py-4 md:px-10">
        <p className="text-[12.5px] text-[var(--muted)]">
          Powered by{' '}
          <Link to="/" className="font-semibold text-[var(--ink)] underline underline-offset-2">
            My Trade Portal
          </Link>
        </p>
        {testflightConfigured() && (
          <a
            href={TESTFLIGHT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[12.5px] font-semibold text-[var(--ink)] underline underline-offset-2"
          >
            Get the app on TestFlight
          </a>
        )}
      </footer>
    </section>
  )
}

export default function ViewQuote() {
  usePageMeta('Your quote — My Trade Portal', 'View the quote your electrician sent you.')
  useNoIndex()
  const { status, error, doc } = usePublicDocument('quote')
  const portal = isPortalMode()

  const replyHref =
    doc?.tenant.reply_email != null
      ? `mailto:${doc.tenant.reply_email}?subject=${encodeURIComponent(
          `Re: your quote${doc.title ? ` — ${doc.title}` : ''}`,
        )}`
      : null

  return (
    <main className="relative flex min-h-screen flex-col">
      {!portal && <Nav />}
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)]">
        {status === 'loading' && (
          <section className="w-full max-w-[720px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <DocumentLoading label="Loading your quote…" />
          </section>
        )}
        {status === 'invalid' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure quote link</p>
            <DocumentInvalid kind="quote" />
          </section>
        )}
        {status === 'error' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure quote link</p>
            <DocumentError message={error} />
          </section>
        )}
        {status === 'loaded' && doc && (
          <DocumentShell doc={doc} heading="Quote">
            {doc.status === 'sent' && replyHref && (
              <div className="mt-[var(--space-xl)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5">
                <p className="text-[14px] leading-relaxed">
                  Happy with the quote, or have a question? Reply directly to your electrician:
                </p>
                <a href={replyHref} className="chip chip--fill mt-[var(--space-md)] justify-center">
                  Reply to your electrician
                </a>
              </div>
            )}
            {doc.status === 'approved' && (
              <p className="mt-[var(--space-xl)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
                You've accepted this quote — {doc.tenant.name} will be in touch to schedule the
                work.
              </p>
            )}
          </DocumentShell>
        )}
      </div>
      {!portal && <Footer />}
    </main>
  )
}
