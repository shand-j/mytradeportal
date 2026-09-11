import { TESTFLIGHT_URL } from '@/lib/site'

export default function FinalCta() {
  return (
    <section id="cta" className="border-b-2 border-[var(--ink)] bg-[var(--ink-deep)] text-[var(--paper-on-dark)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="grid gap-[var(--space-2xl)] md:grid-cols-12 md:items-end">
          <div className="md:col-span-8">
            <p className="reveal spec-label text-[var(--accent)]">No obligation · No tech skills needed</p>
            <h2 className="reveal mt-[var(--space-md)] font-display text-[clamp(2.6rem,6vw,5.5rem)] leading-[0.95] font-extrabold tracking-[-0.02em]" style={{ ['--i' as string]: 1 }}>
              Quote it. Do it. Get paid.
            </h2>
            <p className="reveal mt-[var(--space-lg)] max-w-[46ch] text-[15.5px] leading-[1.75] text-[var(--paper-on-dark-muted)]" style={{ ['--i' as string]: 2 }}>
              Win more jobs. Keep loyal customers. Collect more five-star reviews. Your customers on
              your branded app — by Wednesday.
            </p>
            <div className="reveal mt-[var(--space-xl)]" style={{ ['--i' as string]: 3 }}>
              <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="chip chip--accent">Join the beta →</a>
            </div>
          </div>
          <div className="reveal md:col-span-3 md:col-start-10" style={{ ['--i' as string]: 2 }}>
            <figure className="border border-[var(--paper-on-dark)]/20 bg-[var(--paper)] p-2 shadow-[8px_8px_0_0_rgba(255,193,7,0.9)]">
              <img
                src="/assets/mockups/app-store-invoice.png"
                alt="Invoice issued from the app, on an iPhone"
                width={1444}
                height={3000}
                loading="lazy"
                decoding="async"
                className="mx-auto block h-auto w-full max-w-[240px]"
                draggable={false}
              />
            </figure>
            <p className="mt-[var(--space-xs)] font-mono text-[10px] uppercase tracking-[0.24em] text-[var(--paper-on-dark-muted)]">
              Invoice from the job — sent in seconds
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
