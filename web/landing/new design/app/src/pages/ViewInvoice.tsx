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
import type { PublicDocPayload } from '../lib/public-docs-api'

function BankTransferBlock({ doc, secondary }: { doc: PublicDocPayload; secondary: boolean }) {
  const details = doc.payment_details
  if (!details) return null
  const rows: [string, string][] = [
    ['Account name', details.account_name],
    ['Sort code', details.sort_code],
    ['Account number', details.account_number],
    ['Payment reference', details.reference],
  ].filter((row): row is [string, string] => row[1] !== '')
  if (rows.length === 0) return null
  return (
    <div
      className={`mt-[var(--space-xl)] border-2 p-5 ${
        secondary
          ? 'border-[var(--rule)] bg-[var(--paper-2)]'
          : 'border-[var(--ink)] bg-[var(--paper-2)]'
      }`}
    >
      <p className="text-[14px] font-semibold">
        {secondary ? 'Or pay by bank transfer' : 'Pay by bank transfer'}
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-[var(--muted)]">
        Use the payment reference so {doc.tenant.name} can match your transfer to this invoice.
      </p>
      <dl className="mt-[var(--space-sm)] text-[14px]">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="flex flex-wrap justify-between gap-2 border-b border-[var(--rule)] py-1.5 last:border-b-0"
          >
            <dt className="text-[var(--muted)]">{label}</dt>
            <dd className="font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default function ViewInvoice() {
  usePageMeta('Your invoice — My Trade Portal', 'View and pay the invoice your electrician sent you.')
  useNoIndex()
  const { status, error, doc } = usePublicDocument('invoice')
  const portal = isPortalMode()
  const [searchParams] = useSearchParams()
  const paymentReturning = searchParams.get('paid') === '1'

  const heading = doc?.invoice_number ? `Invoice ${doc.invoice_number}` : 'Invoice'
  const unpaid = doc != null && doc.status !== 'paid' && doc.status !== 'cancelled'
  const canPay = unpaid && doc.payment_url

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
                className="mt-[var(--space-xl)] border-2 border-[var(--ink)] p-4 text-[14px] font-semibold leading-relaxed text-white"
                style={{ backgroundColor: 'var(--brand)' }}
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
                  className="chip chip--fill chip--brand mt-[var(--space-md)] justify-center"
                >
                  Pay this invoice
                </a>
              </div>
            )}
            {unpaid && doc.payment_details && (
              <BankTransferBlock doc={doc} secondary={Boolean(canPay)} />
            )}
            {doc.status === 'paid' && (
              <p
                className="mt-[var(--space-xl)] border-2 border-[var(--ink)] p-4 text-[14px] font-semibold leading-relaxed text-white"
                style={{ backgroundColor: 'var(--brand)' }}
              >
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
