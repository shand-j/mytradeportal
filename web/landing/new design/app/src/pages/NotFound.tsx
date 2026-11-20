import { Link } from 'react-router'
import Footer from '../sections/Footer'
import Nav from '../sections/Nav'
import { usePageMeta } from '../hooks/usePageMeta'

export default function NotFound() {
  usePageMeta(
    'Page not found — My Trade Portal',
    'The My Trade Portal page you requested could not be found.',
  )

  return (
    <main className="relative flex min-h-screen flex-col bg-[var(--paper)]">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-3xl)]">
        <section
          aria-labelledby="not-found-heading"
          className="w-full max-w-[640px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10"
        >
          <p className="spec-label text-[var(--muted)]">404 · Page not found</p>
          <h1
            id="not-found-heading"
            className="mt-[var(--space-xs)] font-display text-[clamp(2rem,5vw,3.5rem)] font-extrabold uppercase leading-[1] tracking-[-0.02em]"
          >
            That page isn&apos;t here
          </h1>
          <p className="mt-[var(--space-md)] max-w-[50ch] text-[15.5px] leading-[1.7] text-[var(--muted)]">
            The address may be wrong, or the page may have moved. Here are a few useful places to
            get you back on track.
          </p>
          <nav
            aria-label="Useful pages"
            className="mt-[var(--space-lg)] flex flex-wrap gap-[var(--space-sm)]"
          >
            <Link to="/" className="chip chip--fill">
              Back to home
            </Link>
            <Link to="/blog" className="chip">
              Read the blog
            </Link>
            <Link to="/help" className="chip">
              Help &amp; guides
            </Link>
          </nav>
        </section>
      </div>
      <Footer />
    </main>
  )
}
