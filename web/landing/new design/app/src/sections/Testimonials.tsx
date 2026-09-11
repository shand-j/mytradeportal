const QUOTES = [
  {
    text: "I used to lose evenings to typing quotes. Now the AI drafts them before I've even packed up my tools. I just tap approve.",
    name: 'Dave Harrington',
    role: 'Electrician, Leeds',
  },
  {
    text: 'My Google reviews went from 14 to over 60 in four months. The app asks every customer automatically — I never have to.',
    name: 'Priya Shah',
    role: 'Electrician, Birmingham',
  },
  {
    text: 'Customers genuinely think I paid thousands for my own app. It makes a one-man band look like a proper firm.',
    name: 'Marcus Doyle',
    role: 'Electrician, Bristol',
  },
]

const STATS: Array<[string, string]> = [
  ['48 hrs', 'from signup to live app'],
  ['24/7', 'AI answering enquiries'],
  ['5.0 ★', 'average customer rating'],
  ['2 min', 'for a customer to install'],
]

export default function Testimonials() {
  return (
    <section id="reviews" className="border-b-2 border-[var(--ink)] bg-[var(--paper-2)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <h2 className="reveal mb-[var(--space-3xl)] max-w-[24ch] font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em] text-[var(--ink)]">
          Tradespeople said it, not us.
        </h2>

        <div className="flex flex-col">
          {QUOTES.map((q, i) => (
            <figure
              key={q.name}
              className="reveal grid gap-[var(--space-sm)] border-t border-[var(--rule)] py-[var(--space-xl)] md:grid-cols-12 md:gap-[var(--space-lg)]"
              style={{ ['--i' as string]: 0 }}
            >
              <blockquote className="font-display text-[clamp(1.25rem,2vw,1.75rem)] leading-[1.3] font-medium tracking-[-0.01em] text-[var(--ink)] md:col-span-8">
                "{q.text}"
              </blockquote>
              <figcaption className="self-end md:col-span-3 md:col-start-10 md:text-right">
                <p className="font-display text-[14px] font-bold uppercase tracking-[0.06em] text-[var(--ink)]">
                  {q.name}
                </p>
                <p className="mt-[var(--space-2xs)] text-[12.5px] text-[var(--muted)]">{q.role}</p>
                <p className="mt-[var(--space-2xs)] font-mono text-[11px] tracking-[0.1em] text-[var(--accent-dark)]">
                  REVIEW {String(i + 1).padStart(2, '0')}
                </p>
              </figcaption>
            </figure>
          ))}
        </div>

        {/* Stat strip — static, tabular */}
        <div className="reveal mt-[var(--space-2xl)] grid grid-cols-2 gap-y-[var(--space-xl)] border-t-2 border-[var(--ink)] pt-[var(--space-xl)] md:grid-cols-4">
          {STATS.map(([v, l]) => (
            <div key={l}>
              <p className="tnum font-display text-[clamp(1.9rem,3vw,2.75rem)] font-extrabold leading-none tracking-[-0.02em] text-[var(--ink)]">
                {v}
              </p>
              <p className="mt-[var(--space-xs)] max-w-[18ch] text-[12.5px] leading-[1.6] text-[var(--muted)]">{l}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
