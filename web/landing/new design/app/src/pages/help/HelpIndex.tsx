import { useEffect } from 'react'
import { Link } from 'react-router'
import Nav from '@/sections/Nav'
import Footer from '@/sections/Footer'
import { usePageMeta } from '@/hooks/usePageMeta'
import { AUDIENCES, articlesFor } from '@/content/help/articles'

export default function HelpIndex() {
  usePageMeta(
    'Help & guides — My Trade Portal',
    'Plain-English guides for electricians using My Trade Portal — quotes, jobs, invoices, team and branding — and for their customers.',
  )

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  return (
    <main className="relative min-h-screen bg-[var(--paper)]">
      <Nav />

      <section className="border-b-2 border-[var(--ink)]">
        <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-3xl)] md:px-10">
          <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
            Help &amp; guides
          </p>
          <h1 className="mt-[var(--space-sm)] max-w-[18ch] font-display text-[clamp(2.4rem,6vw,4.5rem)] font-extrabold uppercase leading-[0.98] tracking-[-0.02em] text-[var(--ink)]">
            How to do
            <br />
            <span className="text-[var(--accent-dark)]">the thing.</span>
          </h1>
          <p className="mt-[var(--space-lg)] max-w-[52ch] text-[16px] leading-[1.75] text-[var(--muted)]">
            Short, plain-English guides: no jargon, no forty-minute videos. For
            electricians running their business on My Trade Portal — and for the
            homeowners they work for.
          </p>
        </div>
      </section>

      {AUDIENCES.map((audience, audienceIndex) => (
        <section
          key={audience.key}
          className={audienceIndex === 0 ? 'border-b-2 border-[var(--ink)]' : ''}
        >
          <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10">
            <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
              {audienceIndex === 0 ? 'Section 1' : 'Section 2'}
            </p>
            <h2 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.4vw,2.6rem)] font-extrabold uppercase leading-[1.05] tracking-[-0.01em] text-[var(--ink)]">
              {audience.title}
            </h2>
            <p className="mt-[var(--space-sm)] max-w-[52ch] text-[15px] leading-[1.7] text-[var(--muted)]">
              {audience.blurb}
            </p>
            <ul className="mt-[var(--space-lg)] grid gap-[var(--space-lg)] md:grid-cols-2">
              {articlesFor(audience.key).map((article) => (
                <li key={article.slug}>
                  <Link
                    to={`/help/${article.slug}`}
                    className="group flex h-full flex-col border-2 border-[var(--ink)] bg-[var(--paper)] p-[var(--space-lg)] transition-colors duration-[length:var(--dur-short)] hover:bg-[var(--paper-2)]"
                  >
                    <h3 className="font-display text-[clamp(1.15rem,1.8vw,1.4rem)] font-extrabold uppercase leading-[1.12] tracking-[-0.01em] text-[var(--ink)] underline decoration-transparent decoration-2 underline-offset-4 transition-colors duration-[length:var(--dur-micro)] group-hover:decoration-[var(--accent)]">
                      {article.title}
                    </h3>
                    <p className="mt-[var(--space-sm)] flex-1 text-[14.5px] leading-[1.7] text-[var(--muted)]">
                      {article.summary}
                    </p>
                    <p className="mt-[var(--space-md)] font-mono text-[12px] font-medium uppercase tracking-[0.18em] text-[var(--ink)]">
                      Read the guide{' '}
                      <span aria-hidden className="text-[var(--accent-dark)] transition-transform duration-[length:var(--dur-micro)] group-hover:translate-x-0.5 inline-block">
                        →
                      </span>
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ))}

      <Footer />
    </main>
  )
}
