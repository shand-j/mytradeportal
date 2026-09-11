import { useEffect } from 'react'
import { Link, useParams } from 'react-router'
import Nav from '@/sections/Nav'
import Footer from '@/sections/Footer'
import { usePageMeta } from '@/hooks/usePageMeta'
import { PostBody } from '@/components/blog/PostBody'
import { getPostBySlug, formatDate } from '@/content/blog/posts'
import { TESTFLIGHT_URL } from '@/lib/site'

export default function BlogPost() {
  const { slug } = useParams<{ slug: string }>()
  const post = slug ? getPostBySlug(slug) : undefined

  usePageMeta(
    post ? `${post.title} — My Trade Portal` : 'Blog — My Trade Portal',
    post
      ? post.description
      : 'Practical, no-nonsense writing for UK tradespeople: AI in the trades, admin time, and honest software comparisons.',
  )

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [slug])

  if (!post) {
    return (
      <main className="relative min-h-screen bg-[var(--paper)]">
        <Nav />
        <section className="mx-auto max-w-[1100px] px-5 py-[var(--space-3xl)] md:px-10">
          <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
            404 · Post not found
          </p>
          <h1 className="mt-[var(--space-sm)] font-display text-[clamp(2rem,5vw,3.5rem)] font-extrabold uppercase leading-[1] tracking-[-0.02em] text-[var(--ink)]">
            Nothing on the bench
          </h1>
          <p className="mt-[var(--space-md)] max-w-[46ch] text-[15.5px] leading-[1.7] text-[var(--muted)]">
            That article doesn’t exist (or has moved). The full list is on the blog.
          </p>
          <Link
            to="/blog"
            className="chip chip--fill mt-[var(--space-lg)] inline-flex"
          >
            Back to the blog
          </Link>
        </section>
        <Footer />
      </main>
    )
  }

  return (
    <main className="relative min-h-screen bg-[var(--paper)]">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'BlogPosting',
            headline: post.title,
            description: post.description,
            datePublished: post.date,
            author: { '@type': 'Organization', name: 'My Trade Portal' },
            publisher: { '@type': 'Organization', name: 'My Trade Portal' },
            mainEntityOfPage: `https://www.mytradeportal.co.uk/blog/${post.slug}`,
          }),
        }}
      />
      <Nav />

      <article>
        <header className="border-b-2 border-[var(--ink)]">
          <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10 md:py-[var(--space-3xl)]">
            <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-[var(--muted)]">
              <Link to="/blog" className="underline decoration-transparent underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:decoration-[var(--accent)]">
                Blog
              </Link>
              {' · '}
              {formatDate(post.date)} · {post.readMinutes} min read
            </p>
            <h1 className="mt-[var(--space-md)] max-w-[22ch] font-display text-[clamp(1.9rem,4.6vw,3.6rem)] font-extrabold uppercase leading-[1.02] tracking-[-0.02em] text-[var(--ink)]">
              {post.title}
            </h1>
            <p className="mt-[var(--space-lg)] max-w-[58ch] border-l-2 border-[var(--accent)] pl-[var(--space-md)] text-[16px] leading-[1.7] text-[var(--muted)]">
              {post.excerpt}
            </p>
          </div>
        </header>

        <div className="mx-auto max-w-[1100px] px-5 py-[var(--space-2xl)] md:px-10">
          <PostBody blocks={post.blocks} />
        </div>
      </article>

      <section className="border-t-2 border-[var(--ink)] bg-[var(--paper-2)]">
        <div className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-[var(--space-md)] px-5 py-[var(--space-xl)] md:px-10">
          <div>
            <p className="font-display text-[clamp(1.2rem,2.2vw,1.7rem)] font-extrabold uppercase leading-[1.1] tracking-[-0.01em] text-[var(--ink)]">
              Tired of the paperwork?
            </p>
            <p className="mt-[var(--space-xs)] max-w-[46ch] text-[14.5px] leading-[1.6] text-[var(--muted)]">
              My Trade Portal drafts quotes, chases customers and sends
              invoices from your iPhone. Free while we’re in beta.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-[var(--space-sm)]">
            <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="chip chip--fill">
              Join the beta
            </a>
            <Link to="/blog" className="chip">
              More from the blog
            </Link>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  )
}
