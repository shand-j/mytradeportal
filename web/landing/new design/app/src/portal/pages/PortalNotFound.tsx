import { Link } from 'react-router'
import Nav from '../../sections/Nav'
import Footer from '../../sections/Footer'
import { usePageMeta } from '../../hooks/usePageMeta'
import { CodeEntry } from '../components/CodeEntry'
import { isPortalMode } from '../host'

/**
 * "Business not found" — an unknown tenant subdomain. Offers the 6-digit
 * code box (which redirects to the right subdomain) plus a link back to the
 * marketing site.
 */
export default function PortalNotFound({ slug }: { slug: string }) {
  usePageMeta('Business not found — My Trade Portal', "We couldn't find that business.")
  const portal = isPortalMode()

  const card = (
    <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Customer portal</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.5rem,3.5vw,2.1rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        We can't find that business
      </h1>
      <p className="mt-[var(--space-md)] text-[14.5px] leading-relaxed text-[var(--muted)]">
        There's no business registered at <span className="font-mono text-[var(--ink)]">{slug}</span>.
        If your electrician gave you a 6-digit code, enter it here and we'll take you to the right
        place:
      </p>
      <div className="mt-[var(--space-md)]">
        <CodeEntry compact />
      </div>
      <p className="mt-[var(--space-lg)] text-[13.5px] text-[var(--muted)]">
        <Link to="/" className="link-arrow">
          Back to mytradeportal.co.uk
        </Link>
      </p>
    </section>
  )

  if (portal) {
    // Rendered standalone by PortalProvider (no marketing chrome in portal mode).
    return (
      <main className="relative flex min-h-screen flex-col items-center justify-center px-5 py-[var(--space-2xl)]">
        {card}
      </main>
    )
  }

  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">{card}</div>
      <Footer />
    </main>
  )
}
