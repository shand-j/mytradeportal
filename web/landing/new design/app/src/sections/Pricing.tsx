import { type Environments, initializePaddle, type Paddle } from '@paddle/paddle-js'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { usePaddlePrices } from '@/hooks/usePaddlePrices'
import { PricingTiers } from '@/constants/pricing-tiers'
import { TESTFLIGHT_URL } from '@/lib/site'

/**
 * Pricing — flat per business, unlimited users, AI unmetered on every plan.
 * Prices are pulled live from Paddle (PricePreview), localised to the
 * visitor's country with tax handled by Paddle, falling back to static GBP
 * launch prices when Paddle isn't configured. During beta every plan is
 * free; shown prices are the launch prices.
 */
export default function Pricing() {
  const [frequency, setFrequency] = useState<'month' | 'year'>('month')
  const [paddle, setPaddle] = useState<Paddle | undefined>()
  // Live Paddle preview stays off until the catalog is rebuilt with the flat
  // per-business prices — the sandbox still returns the old hybrid prices.
  // Set VITE_PADDLE_LIVE_PRICING=true once the new catalog exists.
  const livePricing = import.meta.env.VITE_PADDLE_LIVE_PRICING === 'true'
  const paddleConfigured = livePricing && Boolean(import.meta.env.VITE_PADDLE_CLIENT_TOKEN)

  const { prices, loading } = usePaddlePrices(
    paddleConfigured ? paddle : undefined,
    'OTHERS',
  )

  useEffect(() => {
    if (!paddleConfigured) return
    initializePaddle({
      token: import.meta.env.VITE_PADDLE_CLIENT_TOKEN as string,
      environment: import.meta.env.VITE_PADDLE_ENV as Environments,
    }).then((p) => p && setPaddle(p))
  }, [paddleConfigured])

  return (
    <section id="pricing" className="border-b-2 border-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-3xl)] grid gap-[var(--space-lg)] md:grid-cols-12">
          <div className="md:col-span-7">
            <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em] text-[var(--ink)]">
              Every price on the page.
            </h2>
            <p className="reveal mt-[var(--space-md)] max-w-[44ch] text-[15.5px] leading-[1.75] text-[var(--muted)]" style={{ ['--i' as string]: 1 }}>
              Free while we&apos;re in beta — join TestFlight and every plan is
              unlocked. At launch: one price for your whole business —
              unlimited users, and AI included on every plan. No credits, no
              counting.
            </p>
          </div>

          <div className="reveal self-end md:col-span-4 md:col-start-9" style={{ ['--i' as string]: 2 }}>
            <div
              role="group"
              aria-label="Billing frequency"
              className="flex w-fit border-[1.5px] border-[var(--ink)]"
            >
              <button
                type="button"
                aria-pressed={frequency === 'month'}
                onClick={() => setFrequency('month')}
                className={`px-5 py-2.5 font-display text-[12px] font-bold uppercase tracking-[0.12em] transition-colors duration-[length:var(--dur-micro)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] ${
                  frequency === 'month'
                    ? 'bg-[var(--ink)] text-[var(--paper)]'
                    : 'text-[var(--muted)] hover:text-[var(--ink)]'
                }`}
              >
                Monthly
              </button>
              <button
                type="button"
                aria-pressed={frequency === 'year'}
                onClick={() => setFrequency('year')}
                className={`px-5 py-2.5 font-display text-[12px] font-bold uppercase tracking-[0.12em] transition-colors duration-[length:var(--dur-micro)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] ${
                  frequency === 'year'
                    ? 'bg-[var(--ink)] text-[var(--paper)]'
                    : 'text-[var(--muted)] hover:text-[var(--ink)]'
                }`}
              >
                Yearly
              </button>
            </div>
          </div>
        </div>

        <div className="grid gap-[var(--space-md)] lg:grid-cols-3">
          {PricingTiers.map((tier, i) => {
            const priceId = tier.priceId[frequency] || tier.priceId.month
            const formatted = priceId ? prices[priceId] : undefined
            const priceLoading = loading && formatted === undefined && paddleConfigured
            const shown = formatted ?? tier.fallbackPrice[frequency]
            return (
              <div
                key={tier.id}
                className={`reveal relative flex flex-col p-[var(--space-lg)] md:p-[var(--space-xl)] ${
                  tier.featured
                    ? 'bg-[var(--ink)] text-[var(--paper-on-dark)]'
                    : 'border-[1.5px] border-[var(--ink)] bg-[var(--paper)]'
                }`}
                style={{ ['--i' as string]: i }}
              >
                {tier.featured && (
                  <span className="absolute right-0 top-0 bg-[var(--accent)] px-3 py-1.5 font-display text-[11px] font-bold uppercase tracking-[0.14em] text-[var(--ink-deep)]">
                    Most popular
                  </span>
                )}
                <h3 className="font-display text-[clamp(1.3rem,1.9vw,1.75rem)] font-bold tracking-[0.01em]">
                  {tier.name}
                </h3>
                <p className={`mt-1 text-[13.5px] ${tier.featured ? 'text-[var(--paper-on-dark-muted)]' : 'text-[var(--muted)]'}`}>
                  {tier.tagline}
                </p>
                <p className="tnum mt-[var(--space-lg)] flex items-end gap-2" aria-live="polite">
                  {priceLoading ? (
                    <span className="font-display text-[clamp(2.8rem,4vw,3.75rem)] font-extrabold leading-none tracking-[-0.02em]">
                      ···
                    </span>
                  ) : (
                    <>
                      <span className="font-display text-[clamp(2.8rem,4vw,3.75rem)] font-extrabold leading-none tracking-[-0.02em]">
                        {shown}
                      </span>
                      <span className={`pb-1.5 text-[13px] font-medium ${tier.featured ? 'text-[var(--paper-on-dark-muted)]' : 'text-[var(--muted)]'}`}>
                        per business /{frequency === 'year' ? 'yr' : 'mo'}
                      </span>
                    </>
                  )}
                </p>
                <p className={`spec-label mt-[var(--space-xs)] ${tier.featured ? 'text-[var(--accent)]' : 'text-[var(--accent-dark)]'}`}>
                  {tier.audience}
                </p>
                <p className={`mt-[var(--space-md)] border-[1.5px] px-3 py-2.5 text-[13px] leading-[1.6] ${
                  tier.featured
                    ? 'border-[var(--rule-on-dark)] text-[var(--paper-on-dark)]'
                    : 'border-[var(--rule)] text-[var(--ink)]'
                }`}>
                  {tier.highlight}
                </p>
                <ul className={`mt-[var(--space-lg)] flex-1 space-y-[var(--space-sm)] border-t pt-[var(--space-lg)] text-[14px] ${
                  tier.featured ? 'border-[var(--rule-on-dark)]' : 'border-[var(--rule)]'
                }`}>
                  {tier.features.map((f) => (
                    <li key={f} className="flex gap-[var(--space-sm)]">
                      <svg
                        viewBox="0 0 16 16"
                        className={`mt-1 h-3.5 w-3.5 shrink-0 ${tier.featured ? 'text-[var(--accent)]' : 'text-[var(--accent-dark)]'}`}
                        fill="none"
                        aria-hidden
                      >
                        <path d="m2.5 8.5 3.5 3.5 7.5-8" stroke="currentColor" strokeWidth="2" strokeLinecap="square" />
                      </svg>
                      <span className={tier.featured ? 'text-[var(--paper-on-dark)]' : 'text-[var(--ink)]'}>
                        {f}
                      </span>
                    </li>
                  ))}
                </ul>
                <a
                  href={TESTFLIGHT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`chip mt-[var(--space-xl)] justify-center ${tier.featured ? 'chip--on-dark' : ''}`}
                >
                  Join the beta
                </a>
              </div>
            )
          })}
        </div>

        <div
          className="reveal mt-[var(--space-md)] border-[1.5px] border-[var(--ink)] bg-[var(--paper)] px-5 py-4 md:flex md:items-center md:justify-between md:gap-[var(--space-lg)]"
          style={{ ['--i' as string]: 3 }}
        >
          <p className="font-display text-[13px] font-bold uppercase tracking-[0.12em] text-[var(--ink)]">
            14 days free — full features, no card needed.
          </p>
          <p className="mt-1 text-[13.5px] leading-[1.6] text-[var(--muted)] md:mt-0 md:text-right">
            Send 3 AI quotes during your trial and we&apos;ll extend you to 30 days.
          </p>
        </div>

        <p className="reveal mt-[var(--space-md)] text-[12.5px] leading-[1.7] text-[var(--muted)]" style={{ ['--i' as string]: 4 }}>
          AI is unmetered on every plan, subject to a generous{' '}
          <Link to="/fair-use" className="link-arrow">
            fair-use policy
          </Link>{' '}
          that only exists to stop abuse. Prices shown with local tax where
          applicable, via Paddle.
        </p>
      </div>
    </section>
  )
}
