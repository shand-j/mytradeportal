import { useEffect } from 'react'
import { Link } from 'react-router'
import Nav from '@/sections/Nav'
import Footer from '@/sections/Footer'
import { usePageMeta } from '@/hooks/usePageMeta'
import { posts, formatDate } from '@/content/blog/posts'

export default function BlogIndex() {
  usePageMeta(
    'Blog — My Trade Portal',
    'Practical, no-nonsense writing for UK tradespeople: AI in the trades, how much admin time you can reclaim, and honest software comparisons.',
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
            The blog · For UK tradespeople
          </p>
          <h1 className="mt-[var(--space-sm)] max-w-[18ch] font-display text-[clamp(2.4rem,6vw,4.5rem)] font-extrabold uppercase leading-[0.98] tracking-[-0.02em] text-[var(--ink)]">
            Less admin.
            <br />
            <span className="text-[var(--accent-dark)]">More evenings.</span>
          </h1>
          <p className="mt-[var(--space-lg)] max-w-[52ch] text-[16px] leading-[1.75] text-[var(--muted)]">
            Honest, practical writing on AI in the trades, the admin that eats
            your week, and how to choose software that actually fits a UK
            electrician.
          </p>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10">
          <ul className="grid gap-[var(--space-lg)] md:grid-cols-2">
            {posts.map((post) => (
              <li key={post.slug}>
                <Link
                  to={`/blog/${post.slug}`}
                  className="group flex h-full flex-col border-2 border-[var(--ink)] bg-[var(--paper)] p-[var(--space-lg)] transition-colors duration-[length:var(--dur-short)] hover:bg-[var(--paper-2)]"
                >
                  <p className="font-mono text-[11.5px] uppercase tracking-[0.16em] text-[var(--muted)]">
                    {formatDate(post.date)} · {post.readMinutes} min read
                  </p>
                  <h2 className="mt-[var(--space-sm)] font-display text-[clamp(1.25rem,2vw,1.55rem)] font-extrabold uppercase leading-[1.12] tracking-[-0.01em] text-[var(--ink)] underline decoration-transparent decoration-2 underline-offset-4 transition-colors duration-[length:var(--dur-micro)] group-hover:decoration-[var(--accent)]">
                    {post.title}
                  </h2>
                  <p className="mt-[var(--space-sm)] flex-1 text-[14.5px] leading-[1.7] text-[var(--muted)]">
                    {post.excerpt}
                  </p>
                  <p className="mt-[var(--space-md)] font-mono text-[12px] font-medium uppercase tracking-[0.18em] text-[var(--ink)]">
                    Read the post{' '}
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

      <Footer />
    </main>
  )
}
