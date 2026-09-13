import { useSearchParams } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import {
  DocumentError,
  DocumentInvalid,
  DocumentLoading,
  DocumentShell,
  useNoIndex,
  usePublicDocument,
} from './ViewQuote'
import { isPortalMode } from '../portal/host'

export default function ViewInvoice() {
  usePageMeta('Your invoice — My Trade Portal', 'View and pay the invoice your electrician sent you.')
  useNoIndex()
  const { status, error, doc } = usePublicDocument('invoice')
  const portal = isPortalMode()
  const [searchParams] = useSearchParams()
  const paymentReturning = searchParams.get('paid') === '1'

  const heading = doc?.invoice_number ? `Invoice ${doc.invoice_number}` : 'Invoice'
  const canPay = doc != null && doc.status !== 'paid' && doc.status !== 'cancelled' && doc.payment_url

  return (
    <main className="relative flex min-h-screen flex-col">
      {!portal && <Nav />}
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)]">
        {status === 'loading' && (
          <section className="w-full max-w-[720px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <DocumentLoading label="Loading your invoice…" />
          </section>
        )}
        {status === 'invalid' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure invoice link</p>
            <DocumentInvalid kind="invoice" />
          </section>
        )}
        {status === 'error' && (
          <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Secure invoice link</p>
            <DocumentError message={error} />
          </section>
        )}
        {status === 'loaded' && doc && (
          <DocumentShell doc={doc} heading={heading}>
            {paymentReturning && doc.status !== 'paid' && (
              <p
                role="status"
                className="mt-[var(--space-xl)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]"
              >
                Thank you — your payment is being confirmed. This page will show the invoice as
                paid shortly.
              </p>
            )}
            {canPay && (
              <div className="mt-[var(--space-xl)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5">
                <p className="text-[14px] leading-relaxed">
                  Pay securely online by card — you'll get a receipt from our payment provider.
                </p>
                <a
                  href={doc.payment_url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="chip chip--fill mt-[var(--space-md)] justify-center"
                >
                  Pay this invoice
                </a>
              </div>
            )}
            {doc.status === 'paid' && (
              <p className="mt-[var(--space-xl)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]">
                This invoice is paid — thank you.
              </p>
            )}
          </DocumentShell>
        )}
      </div>
      {!portal && <Footer />}
    </main>
  )
}
