const COMING = ['Plumbers', 'Carpenters', 'HVAC', 'Builders', 'More trades']

/** Slim band: beta is electricians-first, other trades after beta. */
export default function TradesStrip() {
  return (
    <section className="border-b-2 border-[var(--ink)] bg-[var(--paper-2)]">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-[var(--space-lg)] gap-y-[var(--space-sm)] px-5 py-[var(--space-md)] md:px-10">
        <p className="spec-label text-[var(--ink)]">Electricians first</p>
        <span className="hidden h-4 w-px bg-[var(--rule)] md:block" aria-hidden />
        <div className="flex flex-wrap items-center gap-[var(--space-xs)]">
          {COMING.map((t) => (
            <span
              key={t}
              className="border border-[var(--rule)] px-3 py-1 font-display text-[11.5px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
            >
              {t}
            </span>
          ))}
        </div>
        <span className="hidden h-4 w-px bg-[var(--rule)] md:block" aria-hidden />
        <p className="spec-label text-[var(--accent-dark)]">Coming after beta</p>
      </div>
    </section>
  )
}
