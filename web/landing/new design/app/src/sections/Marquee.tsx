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

/** Job-types band — fixed and fully visible on desktop; on mobile it becomes a
 *  single-line row the user swipes through (native scroll with snap points).
 *  No auto-rotation: anything that moves on its own felt cheap. */
export default function Marquee() {
  return (
    <section aria-label="Job types covered" className="border-b-2 border-[var(--ink)] bg-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-md)] md:px-10">
        <ul className="flex items-baseline gap-x-[var(--space-lg)] max-md:snap-x max-md:snap-mandatory max-md:flex-nowrap max-md:gap-x-[var(--space-md)] max-md:overflow-x-auto max-md:whitespace-nowrap max-md:[scrollbar-width:none] max-md:[&::-webkit-scrollbar]:hidden md:flex-wrap md:gap-y-[var(--space-2xs)]">
          {JOBS.map((job, i) => (
            <li key={job} className="flex shrink-0 snap-start items-baseline gap-[var(--space-md)] md:gap-[var(--space-lg)]">
              <span className="whitespace-nowrap font-display text-[15px] font-bold uppercase tracking-[0.1em] text-[var(--paper-on-dark)]">
                {job}
              </span>
              {i < JOBS.length - 1 && (
                <span className="font-display text-[15px] font-bold text-[var(--accent)]" aria-hidden>
                  +
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
