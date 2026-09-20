import { useEffect } from 'react'
import { Link, useParams } from 'react-router'
import Nav from '@/sections/Nav'
import Footer from '@/sections/Footer'
import { usePageMeta } from '@/hooks/usePageMeta'
import { HelpBody } from '@/components/help/HelpBody'
import { AUDIENCES, getArticleBySlug } from '@/content/help/articles'

export default function HelpArticle() {
  const { slug } = useParams<{ slug: string }>()
  const article = slug ? getArticleBySlug(slug) : undefined

  usePageMeta(
    article ? `${article.title} — My Trade Portal help` : 'Help & guides — My Trade Portal',
    article
      ? article.summary
      : 'Plain-English guides for electricians using My Trade Portal, and for their customers.',
  )

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [slug])

  if (!article) {
    return (
      <main className="relative min-h-screen bg-[var(--paper)]">
        <Nav />
        <section className="mx-auto max-w-[1100px] px-5 py-[var(--space-3xl)] md:px-10">
          <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
            404 · Guide not found
          </p>
          <h1 className="mt-[var(--space-sm)] font-display text-[clamp(2rem,5vw,3.5rem)] font-extrabold uppercase leading-[1] tracking-[-0.02em] text-[var(--ink)]">
            Nothing on the bench
          </h1>
          <p className="mt-[var(--space-md)] max-w-[46ch] text-[15.5px] leading-[1.7] text-[var(--muted)]">
            That guide doesn’t exist (or has moved). The full list is in the help centre.
          </p>
          <Link
            to="/help"
            className="chip chip--fill mt-[var(--space-lg)] inline-flex"
          >
            Back to help &amp; guides
          </Link>
        </section>
        <Footer />
      </main>
    )
  }

  const audience = AUDIENCES.find((a) => a.key === article.audience)

  return (
    <main className="relative min-h-screen bg-[var(--paper)]">
      <Nav />

      <article>
        <header className="border-b-2 border-[var(--ink)]">
          <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10 md:py-[var(--space-3xl)]">
            <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
              <Link to="/help" className="underline decoration-transparent underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:decoration-[var(--accent)]">
                Help &amp; guides
              </Link>
              {audience && ` · ${audience.title}`}
            </p>
            <h1 className="mt-[var(--space-md)] max-w-[22ch] font-display text-[clamp(1.9rem,4.6vw,3.6rem)] font-extrabold uppercase leading-[1.02] tracking-[-0.02em] text-[var(--ink)]">
              {article.title}
            </h1>
            <p className="mt-[var(--space-lg)] max-w-[58ch] border-l-2 border-[var(--accent)] pl-[var(--space-md)] text-[16px] leading-[1.7] text-[var(--muted)]">
              {article.summary}
            </p>
          </div>
        </header>

        <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10">
          <HelpBody blocks={article.blocks} />
        </div>
      </article>

      <section className="border-t-2 border-[var(--ink)] bg-[var(--paper-2)]">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-[var(--space-md)] px-5 py-[var(--space-xl)] md:px-10">
          <div>
            <p className="font-display text-[clamp(1.2rem,2.2vw,1.7rem)] font-extrabold uppercase leading-[1.1] tracking-[-0.01em] text-[var(--ink)]">
              Still stuck?
            </p>
            <p className="mt-[var(--space-xs)] max-w-[46ch] text-[14.5px] leading-[1.6] text-[var(--muted)]">
              Reply to any email we’ve sent you, or use the message thread in the
              app — a real person reads it.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-[var(--space-sm)]">
            <Link to="/help" className="chip">
              All guides
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  )
}
