const PAINS = [
  {
    title: 'Losing quotes',
    body: "A customer messages you mid-job. You mean to reply tonight. By then they've already booked someone who answered in five minutes.",
    stat: '78%',
    statLabel: 'of customers hire whoever responds first',
  },
  {
    title: 'Evenings eaten by admin',
    body: 'Quotes, invoices and appointment juggling — all done at the kitchen table after a full day on the tools. Unpaid, every week.',
    stat: '6hrs',
    statLabel: 'of weekly admin for the average sole trader',
  },
  {
    title: 'Reviews you never got',
    body: 'Every finished job is a five-star review waiting to happen — but nobody remembers to ask, so your Google profile gathers dust.',
    stat: '9/10',
    statLabel: 'of customers read reviews before calling',
  },
]

export default function Problem() {
  return (
    <section className="border-b-2 border-[var(--ink)] bg-[var(--ink)] text-[var(--paper-on-dark)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-2xl)] max-w-[52ch]">
          <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em]">
            Still running your business from WhatsApp?
          </h2>
          <p className="reveal mt-[var(--space-md)] text-[15.5px] leading-[1.75] text-[var(--paper-on-dark-muted)]" style={{ ['--i' as string]: 1 }}>
            Quotes buried in chat threads. Board photos mixed in with family pictures. Customers who
            meant to leave a review but forgot. It's not a workload problem — it's a tooling problem.
          </p>
        </div>

        <div className="border-t border-[var(--rule-on-dark)]">
          {PAINS.map((p, i) => (
            <div
              key={p.title}
              className="reveal grid gap-[var(--space-sm)] border-b border-[var(--rule-on-dark)] py-[var(--space-xl)] md:grid-cols-12 md:items-baseline md:gap-[var(--space-lg)]"
              style={{ ['--i' as string]: i }}
            >
              <h3 className="font-display text-[clamp(1.3rem,1.9vw,1.75rem)] font-bold leading-[1.1] tracking-[-0.01em] md:col-span-3">
                {p.title}
              </h3>
              <p className="max-w-[52ch] text-[14.5px] leading-[1.75] text-[var(--paper-on-dark-muted)] md:col-span-6">
                {p.body}
              </p>
              <div className="md:col-span-3 md:text-right">
                <p className="tnum font-display text-[clamp(2rem,3.4vw,3rem)] font-extrabold leading-none tracking-[-0.02em] text-[var(--accent)]">
                  {p.stat}
                </p>
                <p className="mt-[var(--space-xs)] text-[12.5px] leading-[1.6] text-[var(--paper-on-dark-muted)] md:ml-auto md:max-w-[22ch]">
                  {p.statLabel}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
