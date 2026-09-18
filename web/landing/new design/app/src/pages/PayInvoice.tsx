import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { Elements } from '@stripe/react-stripe-js'
import { usePageMeta } from '../hooks/usePageMeta'
import {
  DocumentError,
  DocumentInvalid,
  DocumentLoading,
  formatMoney,
  useNoIndex,
  usePublicDocument,
} from './ViewQuote'
import { buildElementsOptions, getStripe, PUBLISHABLE_KEY } from '../portal/pay/stripe'
import { PaymentForm } from '../portal/pay/PaymentForm'
import { PayShell } from '../portal/pay/PayShell'

export default function PayInvoice() {
  usePageMeta('Pay your invoice — My Trade Portal', 'Pay the invoice your electrician sent you, securely by card.')
  useNoIndex()
  const { token = '' } = useParams()
  const [searchParams] = useSearchParams()
  const paymentIntentId = searchParams.get('pi')
  const clientSecret = searchParams.get('cs')
  const paymentReturning = searchParams.get('paid') === '1'
  const { status, error, doc } = usePublicDocument('invoice')

  const linkParamsValid = Boolean(token && paymentIntentId && clientSecret)
  const brandColor = doc?.tenant.brand_color || '#0F1E26'

  const elementsOptions = useMemo(
    () => (clientSecret ? buildElementsOptions(clientSecret, brandColor) : null),
    [clientSecret, brandColor],
  )

  const showInvalid = !linkParamsValid || status === 'invalid'

  const shellProps = doc
    ? {
        businessName: doc.tenant.name,
        logoUrl: doc.tenant.logo_url,
        brandColor,
        reference: doc.invoice_number ? `Invoice ${doc.invoice_number}` : 'Invoice',
        currency: doc.currency,
        total: doc.total,
        title: doc.title,
      }
    : null

  return (
    <main className="relative flex min-h-screen flex-col">
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)]">
        {showInvalid && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure payment link</p>
            <DocumentInvalid kind="invoice" />
          </section>
        )}
        {!showInvalid && status === 'loading' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <DocumentLoading label="Loading your payment…" />
          </section>
        )}
        {!showInvalid && status === 'error' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure payment link</p>
            <DocumentError message={error} />
          </section>
        )}
        {!showInvalid && status === 'loaded' && doc && shellProps && !PUBLISHABLE_KEY && (
          <PayShell {...shellProps}>
            <div className="mt-[var(--space-lg)]" role="alert">
              <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
                Card payments aren't available right now — please try again later or contact{' '}
                {doc.tenant.name} directly.
              </p>
            </div>
          </PayShell>
        )}
        {!showInvalid && status === 'loaded' && doc && shellProps && paymentReturning && doc.status !== 'paid' && (
          <PayShell {...shellProps}>
            <p
              role="status"
              className="mt-[var(--space-lg)] border-2 border-[var(--ink)] p-4 text-[14px] font-semibold leading-relaxed text-white"
              style={{ backgroundColor: 'var(--brand)' }}
            >
              Thank you — your payment is being confirmed. This page will show the invoice as
              paid shortly.
            </p>
            <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
              <Link to={`/invoice/${token}`} className="link-arrow">
                View your invoice
              </Link>
            </p>
          </PayShell>
        )}
        {!showInvalid && status === 'loaded' && doc && shellProps && PUBLISHABLE_KEY && doc.status === 'paid' && (
          <PayShell {...shellProps}>
            <p
              className="mt-[var(--space-lg)] border-2 border-[var(--ink)] p-4 text-[14px] font-semibold leading-relaxed text-white"
              style={{ backgroundColor: 'var(--brand)' }}
            >
              This invoice is already paid — thank you.
            </p>
            <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
              <Link to={`/invoice/${token}`} className="link-arrow">
                View your invoice
              </Link>
            </p>
          </PayShell>
        )}
        {!showInvalid &&
          status === 'loaded' &&
          doc &&
          shellProps &&
          PUBLISHABLE_KEY &&
          doc.status !== 'paid' &&
          !paymentReturning &&
          elementsOptions && (
            <PayShell {...shellProps}>
              <Elements stripe={getStripe(PUBLISHABLE_KEY)} options={elementsOptions}>
                <PaymentForm
                  returnUrl={`${window.location.origin}/invoice/${token}?paid=1`}
                  submitLabel={`Pay ${formatMoney(doc.currency, doc.total)}`}
                />
              </Elements>
            </PayShell>
          )}
      </div>
    </main>
  )
}
