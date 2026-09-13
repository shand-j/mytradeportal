import { Link } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import { isPortalMode } from '../portal/host'

/**
 * Fair-use policy — AI is included on every plan with no counting. A generous
 * monthly threshold exists purely to stop abuse, and no account is ever hard
 * limited without a human review and a conversation first.
 */
export default function FairUse() {
  usePageMeta(
    'Fair-use policy — My Trade Portal',
    'AI is included on every My Trade Portal plan with no credits and no counting — our fair-use policy exists only to stop abuse.',
  )

  const portal = isPortalMode()

  return (
    <main className="relative flex min-h-screen flex-col">
      {!portal && <Nav />}
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)] md:py-[var(--space-3xl)]">
        <section className="w-full max-w-[720px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
          <p className="spec-label text-[var(--muted)]">Policy</p>
          <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.5rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            Fair-use policy
          </h1>
          <p className="mt-[var(--space-md)] text-[15px] leading-[1.75] text-[var(--muted)]">
            The short version: use the AI as much as your work needs. Almost
            nobody will ever brush against this policy.
          </p>

          <div className="mt-[var(--space-lg)] space-y-[var(--space-lg)] text-[14.5px] leading-[1.75]">
            <div>
              <h2 className="font-display text-[15px] font-bold uppercase tracking-[0.08em] text-[var(--ink)]">
                AI is included on every plan
              </h2>
              <p className="mt-[var(--space-xs)]">
                Every plan — Sole Trader, Pro, and Team — comes with AI built
                in. There are no credits to buy, no tokens to top up, and no
                meter running in the background. Quote, chat, and analyse
                photos as much as the job needs.
              </p>
            </div>

            <div>
              <h2 className="font-display text-[15px] font-bold uppercase tracking-[0.08em] text-[var(--ink)]">
                Why a threshold exists at all
              </h2>
              <p className="mt-[var(--space-xs)]">
                Each business gets a generous allowance — around 500 AI
                actions a month — purely to stop abuse: scripted scraping,
                reselling access, that sort of thing. It&apos;s set far above
                what even the busiest firm uses in a normal month, so genuine
                users will never notice it.
              </p>
            </div>

            <div>
              <h2 className="font-display text-[15px] font-bold uppercase tracking-[0.08em] text-[var(--ink)]">
                We&apos;ll always talk to you first
              </h2>
              <p className="mt-[var(--space-xs)]">
                If your account ever goes past that threshold, we&apos;ll
                always talk to you before limiting anything. There is never a
                hard block without a human reviewing your account first — and
                if it turns out you just had a monster month, we&apos;ll sort
                something out, not switch you off.
              </p>
            </div>

            <div>
              <h2 className="font-display text-[15px] font-bold uppercase tracking-[0.08em] text-[var(--ink)]">
                Questions?
              </h2>
              <p className="mt-[var(--space-xs)]">
                If you think your workload might be unusual, just ask us —
                we&apos;d rather hear about it than have you worry about it.
              </p>
            </div>
          </div>

          <p className="mt-[var(--space-lg)] border-t-2 border-[var(--rule)] pt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
            <Link to="/#pricing" className="link-arrow">
              Back to pricing
            </Link>
          </p>
        </section>
      </div>
      {!portal && <Footer />}
    </main>
  )
}
