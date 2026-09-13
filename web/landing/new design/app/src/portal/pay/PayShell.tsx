import { Link } from 'react-router'

/**
 * Branded payment card shell shared by the token pay page and the portal.
 * Branding follows the DocumentShell pattern: inline brand colour on the
 * header band, logo + business name, big total.
 */
export function PayShell({
  businessName,
  logoUrl,
  brandColor,
  reference,
  currency,
  total,
  title,
  children,
}: {
  businessName: string
  logoUrl: string | null
  brandColor: string
  reference: string
  currency: string
  total: string
  title?: string | null
  children?: React.ReactNode
}) {
  return (
    <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)]">
      <header
        className="flex items-center gap-[var(--space-md)] border-b-2 border-[var(--ink)] px-6 py-5"
        style={{ backgroundColor: brandColor }}
      >
        {logoUrl && (
          <img
            src={logoUrl}
            alt={`${businessName} logo`}
            className="h-10 w-10 border-2 border-white/40 bg-white object-contain"
          />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-[18px] font-extrabold uppercase tracking-[0.02em] text-white">
            Pay {businessName}
          </p>
          <p className="text-[12px] uppercase tracking-[0.1em] text-white/75">Secure payment</p>
        </div>
      </header>

      <div className="px-6 py-[var(--space-lg)]">
        <p className="spec-label text-[var(--muted)]">{reference}</p>
        <p className="mt-[var(--space-2xs)] font-display text-[clamp(2rem,6vw,2.6rem)] font-extrabold leading-none tracking-[0.01em]">
          {formatAmount(currency, total)}
        </p>
        {title && <p className="mt-[var(--space-sm)] text-[14px] text-[var(--muted)]">{title}</p>}
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

function formatAmount(currency: string, value: string): string {
  const amount = Number(value)
  if (Number.isNaN(amount)) return value
  return new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format(amount)
}
