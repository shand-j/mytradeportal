import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { loadStripe, type Stripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import { usePageMeta } from '../hooks/usePageMeta'
import type { PublicDocPayload } from '../lib/public-docs-api'
import {
  DocumentError,
  DocumentInvalid,
  DocumentLoading,
  formatMoney,
  useNoIndex,
  usePublicDocument,
} from './ViewQuote'

const PUBLISHABLE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined

let stripePromise: Promise<Stripe | null> | null = null

function getStripe(key: string): Promise<Stripe | null> {
  if (!stripePromise) stripePromise = loadStripe(key)
  return stripePromise
}

function PaymentForm({ token, doc }: { token: string; doc: PublicDocPayload }) {
  const stripe = useStripe()
  const elements = useElements()
  const [processing, setProcessing] = useState(false)
  const [paymentError, setPaymentError] = useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!stripe || !elements || processing) return
    setProcessing(true)
    setPaymentError(null)
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/invoice/${token}?paid=1`,
      },
    })
    // Reaching here means the payment failed without a redirect (declined
    // card, validation error) — success navigates away to the return_url.
    setProcessing(false)
    setPaymentError(
      error.message ?? 'Your payment could not be processed — check your details and try again.',
    )
  }

  return (
    <form onSubmit={handleSubmit} className="mt-[var(--space-lg)]">
      <PaymentElement />
      {paymentError && (
        <p
          role="alert"
          className="mt-[var(--space-md)] border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed"
        >
          {paymentError}
        </p>
      )}
      <button
        type="submit"
        disabled={!stripe || !elements || processing}
        className="chip chip--fill mt-[var(--space-lg)] w-full justify-center disabled:cursor-not-allowed disabled:opacity-60"
      >
        {processing ? 'Processing…' : `Pay ${formatMoney(doc.currency, doc.total)}`}
      </button>
      <p className="mt-[var(--space-sm)] text-center text-[12.5px] text-[var(--muted)]">
        Secured by Stripe — your card details never touch our servers.
      </p>
    </form>
  )
}

function PayShell({
  doc,
  children,
}: {
  doc: PublicDocPayload
  children?: React.ReactNode
}) {
  const brand = doc.tenant.brand_color || '#0F1E26'
  const invoiceRef = doc.invoice_number ? `Invoice ${doc.invoice_number}` : 'Invoice'
  return (
    <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)]">
      <header
        className="flex items-center gap-[var(--space-md)] border-b-2 border-[var(--ink)] px-6 py-5"
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
            Pay {doc.tenant.name}
          </p>
          <p className="text-[12px] uppercase tracking-[0.1em] text-white/75">Secure payment</p>
        </div>
      </header>

      <div className="px-6 py-[var(--space-lg)]">
        <p className="spec-label text-[var(--muted)]">{invoiceRef}</p>
        <p className="mt-[var(--space-2xs)] font-display text-[clamp(2rem,6vw,2.6rem)] font-extrabold leading-none tracking-[0.01em]">
          {formatMoney(doc.currency, doc.total)}
        </p>
        {doc.title && <p className="mt-[var(--space-sm)] text-[14px] text-[var(--muted)]">{doc.title}</p>}
        {children}
      </div>

      <footer className="border-t-2 border-[var(--ink)] bg-[var(--paper-2)] px-6 py-4">
        <p className="text-[12.5px] text-[var(--muted)]">
          Powered by{' '}
          <Link to="/" className="font-semibold text-[var(--ink)] underline underline-offset-2">
            My Trade Portal
          </Link>
        </p>
      </footer>
    </section>
  )
}

export default function PayInvoice() {
  usePageMeta('Pay your invoice — My Trade Portal', 'Pay the invoice your electrician sent you, securely by card.')
  useNoIndex()
  const { token = '' } = useParams()
  const [searchParams] = useSearchParams()
  const paymentIntentId = searchParams.get('pi')
  const clientSecret = searchParams.get('cs')
  const { status, error, doc } = usePublicDocument('invoice')

  const linkParamsValid = Boolean(token && paymentIntentId && clientSecret)
  const brandColor = doc?.tenant.brand_color || '#0F1E26'

  const elementsOptions = useMemo(
    () =>
      clientSecret
        ? {
            clientSecret,
            appearance: {
              theme: 'stripe' as const,
              variables: {
                colorPrimary: brandColor,
                borderRadius: '2px',
              },
            },
          }
        : null,
    [clientSecret, brandColor],
  )

  const showInvalid = !linkParamsValid || status === 'invalid'

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
        {!showInvalid && status === 'loaded' && doc && !PUBLISHABLE_KEY && (
          <PayShell doc={doc}>
            <div className="mt-[var(--space-lg)]" role="alert">
              <p className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
                Card payments aren't available right now — please try again later or contact{' '}
                {doc.tenant.name} directly.
              </p>
            </div>
          </PayShell>
        )}
        {!showInvalid && status === 'loaded' && doc && PUBLISHABLE_KEY && doc.status === 'paid' && (
          <PayShell doc={doc}>
            <p className="mt-[var(--space-lg)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
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
          PUBLISHABLE_KEY &&
          doc.status !== 'paid' &&
          elementsOptions && (
            <PayShell doc={doc}>
              <Elements stripe={getStripe(PUBLISHABLE_KEY)} options={elementsOptions}>
                <PaymentForm token={token} doc={doc} />
              </Elements>
            </PayShell>
          )}
      </div>
    </main>
  )
}
