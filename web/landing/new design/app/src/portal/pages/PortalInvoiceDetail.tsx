import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { Elements } from '@stripe/react-stripe-js'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { RequireAuth } from '../components/auth'
import { usePageMeta } from '../../hooks/usePageMeta'
import { getInvoice, SessionExpiredError, type CustomerInvoice } from '../api'
import { buildElementsOptions, getStripe, PUBLISHABLE_KEY } from '../pay/stripe'
import { PaymentForm } from '../pay/PaymentForm'
import { DocumentLoading, formatDate, formatMoney, StatusBadge } from '../../pages/ViewQuote'

function InvoiceDetail({ id }: { id: string }) {
  const { slug, config, sessionVersion } = usePortal()
  const [searchParams] = useSearchParams()
  const paymentReturning = searchParams.get('paid') === '1'
  const [status, setStatus] = useState<'loading' | 'error' | 'loaded'>('loading')
  const [error, setError] = useState('')
  const [invoice, setInvoice] = useState<CustomerInvoice | null>(null)

  useEffect(() => {
    let cancelled = false
    getInvoice(slug, id)
      .then((data) => {
        if (cancelled) return
        setInvoice(data)
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
  }, [slug, id, sessionVersion])

  const brandColor = config.primary_color || '#0F1E26'
  const clientSecret = invoice?.payment_client_secret ?? null
  const elementsOptions = useMemo(
    () => (clientSecret ? buildElementsOptions(clientSecret, brandColor) : null),
    [clientSecret, brandColor],
  )

  if (status === 'loading') return <DocumentLoading label="Loading your invoice…" />
  if (status === 'error') {
    return (
      <p role="alert" className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        {error}
      </p>
    )
  }
  if (!invoice) return null

  const vatPercent = Math.round(Number(invoice.vat_rate) * 100)
  const unpaid = invoice.status !== 'paid' && invoice.status !== 'cancelled'

  return (
    <section
      className="border-2 border-[var(--ink)] bg-[var(--paper)]"
      style={{ '--brand': brandColor } as React.CSSProperties}
    >
      <div className="px-6 py-[var(--space-lg)] md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-display text-[clamp(1.2rem,3vw,1.7rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
              Invoice {invoice.invoice_number}
            </h2>
            <p className="mt-1 text-[13px] text-[var(--muted)]">
              Issued {formatDate(invoice.issue_date)}
              {invoice.due_date && <> · due by {formatDate(invoice.due_date)}</>}
              {invoice.paid_at && <> · paid {formatDate(invoice.paid_at)}</>}
            </p>
          </div>
          <StatusBadge status={invoice.status} />
        </div>

        {paymentReturning && unpaid && (
          <p role="status" className="mt-[var(--space-md)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
            Thank you — your payment is being confirmed. This page will show the invoice as paid
            shortly.
          </p>
        )}

        {invoice.notes && (
          <p className="mt-[var(--space-md)] whitespace-pre-line text-[14.5px] leading-relaxed">
            {invoice.notes}
          </p>
        )}

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
            {invoice.line_items.map((line) => (
              <tr key={line.id} className="border-b border-[var(--rule)]">
                <td className="py-2.5 pr-3 align-top">{line.description}</td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right align-top">
                  {Number(line.quantity)} {line.unit !== 'ea' ? line.unit : ''}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right align-top">
                  {formatMoney('GBP', line.unit_price)}
                </td>
                <td className="whitespace-nowrap py-2.5 pl-3 text-right align-top">
                  {formatMoney('GBP', line.total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="ml-auto mt-[var(--space-md)] w-full max-w-[280px] text-[14px]">
          <div className="flex justify-between py-1">
            <dt className="text-[var(--muted)]">Subtotal (ex VAT)</dt>
            <dd>{formatMoney('GBP', invoice.subtotal)}</dd>
          </div>
          <div className="flex justify-between border-b border-[var(--rule)] py-1">
            <dt className="text-[var(--muted)]">VAT{vatPercent ? ` (${vatPercent}%)` : ''}</dt>
            <dd>{formatMoney('GBP', invoice.vat_amount)}</dd>
          </div>
          <div className="flex justify-between py-2 text-[16px] font-extrabold">
            <dt>Total</dt>
            <dd>{formatMoney('GBP', invoice.total)}</dd>
          </div>
        </dl>

        {invoice.status === 'paid' && (
          <p className="mt-[var(--space-xl)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
            This invoice is paid — thank you.
          </p>
        )}

        {unpaid && (
          <div className="mt-[var(--space-xl)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5">
            {invoice.payment_url ? (
              <>
                <p className="text-[14px] leading-relaxed">
                  Pay securely online by card — you'll get a receipt from our payment provider.
                </p>
                <a
                  href={invoice.payment_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="chip chip--fill mt-[var(--space-md)] justify-center"
                >
                  Pay securely now
                </a>
              </>
            ) : elementsOptions && PUBLISHABLE_KEY ? (
              <>
                <p className="text-[14px] leading-relaxed">Pay securely online by card.</p>
                <Elements stripe={getStripe(PUBLISHABLE_KEY)} options={elementsOptions}>
                  <PaymentForm
                    returnUrl={`${window.location.origin}/invoices/${invoice.id}?paid=1`}
                    submitLabel={`Pay ${formatMoney('GBP', invoice.total)}`}
                  />
                </Elements>
              </>
            ) : (
              <>
                <p className="text-[14px] leading-relaxed">
                  To pay online, use the secure pay link in your invoice email — or call{' '}
                  {config.name} to pay another way.
                </p>
                {config.phone && (
                  <a href={`tel:${config.phone}`} className="chip mt-[var(--space-md)] justify-center">
                    Call {config.phone}
                  </a>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

export default function PortalInvoiceDetail() {
  const { config } = usePortal()
  const { id = '' } = useParams()
  usePageMeta(`Your invoice — ${config.name}`, `Invoice from ${config.name}.`)
  return (
    <PortalShell>
      <p className="mb-[var(--space-sm)] text-[13px]">
        <Link to="/invoices" className="link-arrow">
          ← All invoices
        </Link>
      </p>
      <RequireAuth>
        <InvoiceDetail id={id} />
      </RequireAuth>
    </PortalShell>
  )
}
