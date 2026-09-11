const JOBS = [
  'Consumer units',
  'EV chargers',
  'EICR testing',
  'Fuse boards',
  'Full rewires',
  'Outdoor power',
  'Fault finding',
  'Smart lighting',
]

/** Static job-types band — the work the beta is built around. */
export default function Marquee() {
  return (
    <section aria-label="Job types covered" className="border-b-2 border-[var(--ink)] bg-[var(--ink)]">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-baseline gap-x-[var(--space-lg)] gap-y-[var(--space-2xs)] px-5 py-[var(--space-md)] md:px-10">
        {JOBS.map((job, i) => (
          <span key={job} className="flex items-baseline gap-[var(--space-lg)]">
            <span className="whitespace-nowrap font-display text-[15px] font-bold uppercase tracking-[0.1em] text-[var(--paper-on-dark)]">
              {job}
            </span>
            {i < JOBS.length - 1 && (
              <span className="font-display text-[15px] font-bold text-[var(--accent)]" aria-hidden>+</span>
            )}
          </span>
        ))}
      </div>
    </section>
  )
}
