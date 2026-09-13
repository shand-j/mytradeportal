import Nav from '../../sections/Nav'
import Footer from '../../sections/Footer'
import { usePageMeta } from '../../hooks/usePageMeta'
import { CodeEntry } from '../components/CodeEntry'

/**
 * www-mode 6-digit code redemption page (/code). Portal home deliberately
 * has no code box — in portal mode you're already on the tenant's site.
 */
export default function CodeEntryPage() {
  usePageMeta(
    'Find your electrician — My Trade Portal',
    'Enter the 6-digit code from your electrician to reach their customer portal.',
  )
  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        <section className="w-full max-w-[520px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
          <p className="spec-label text-[var(--muted)]">Customer portal</p>
          <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.5rem,3.5vw,2.1rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            Find your electrician's portal
          </h1>
          <p className="mt-[var(--space-md)] text-[14.5px] leading-relaxed text-[var(--muted)]">
            Enter the 6-digit code from your electrician's card, van or sticker — we'll take you
            straight to their page, where you can request a quote, follow your job and pay online.
          </p>
          <div className="mt-[var(--space-lg)]">
            <CodeEntry />
          </div>
        </section>
      </div>
      <Footer />
    </main>
  )
}
