import { Link } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import { isPortalMode } from '../portal/host'
import { PortalShell } from '../portal/components/PortalShell'

export default function Terms() {
  usePageMeta(
    'Terms of Service — My Trade Portal',
    'Terms of Service for My Trade Portal.',
  )

  const content = (
    <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Legal</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.5rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Terms of Service
      </h1>
      <p className="mt-[var(--space-md)] border-2 border-[var(--rule)] p-4 text-[14.5px] leading-[1.75] text-[var(--muted)]">
        The approved Terms of Service are pending publication. This page is
        reserved for the final, legally approved wording and must not be used
        as a substitute for terms supplied and approved by Legal/compliance.
      </p>
      <p className="mt-[var(--space-lg)] text-[13.5px] text-[var(--muted)]">
        <Link to="/fair-use" className="link-arrow">Fair-use policy</Link>
        {' · '}
        <Link to="/privacy" className="link-arrow">Privacy notice</Link>
      </p>
    </section>
  )

  if (isPortalMode()) {
    return <PortalShell>{content}</PortalShell>
  }

  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)] md:py-[var(--space-3xl)]">
        <div className="w-full max-w-[720px]">{content}</div>
      </div>
      <Footer />
    </main>
  )
}
