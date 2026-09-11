const STOPS = [
  {
    title: 'Your brand, from sign-in',
    body: "Customers download one app and it wears your name, your logo and your colours the moment they sign in. Want your own App Store listing too? That's the add-on.",
    img: '/assets/mockups/app-store-entry-role-select-concrete-hand.jpg',
    alt: 'App entry screen re-skinned to the business brand',
  },
  {
    title: 'Quote intake, built for the job',
    body: "Property type, consumer unit location, parking, photos — the app asks the questions you'd ask on the phone, before you ever call back.",
    img: '/assets/mockups/app-store-quotes-generating-construction.jpg',
    alt: 'Structured quote intake form for an electrical job',
  },
  {
    title: 'AI-drafted quotes',
    body: 'Line items, VAT and a confidence score drafted in seconds. You check every number before it goes out — the AI does the typing, you do the pricing.',
    img: '/assets/mockups/app-store-review-quote-concrete-hand.jpg',
    alt: 'AI-drafted quote with line items and VAT',
  },
  {
    title: 'In-app chat',
    body: 'Ask for photos or book a site visit with one-tap quick requests. No more quote threads buried in WhatsApp.',
    img: '/assets/mockups/app-store-customer-ai-chat-construction.jpg',
    alt: 'In-app chat with a quick info request',
  },
  {
    title: 'Every lead in one place',
    body: 'New, flagged, sent, accepted — sorted by urgency with the money on the card. £545–£620 beats "somewhere in my messages".',
    img: '/assets/mockups/app-store-quotes-pipeline-concrete-hand.jpg',
    alt: 'Quotes list sorted by status and value',
  },
  {
    title: 'Customer history',
    body: 'Lifetime value, quotes, jobs and notes on one screen. "Has a dog, board is in the garage" — the details that make you look good.',
    img: '/assets/mockups/app-store-dashboard-construction.jpg',
    alt: 'Customer record with history and notes',
  },
]

export default function Showcase() {
  return (
    <section id="features" className="border-b-2 border-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-3xl)] max-w-[46ch]">
          <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em] text-[var(--ink)]">
            Take the tour.
          </h2>
          <p className="reveal mt-[var(--space-md)] text-[15.5px] leading-[1.75] text-[var(--muted)]" style={{ ['--i' as string]: 1 }}>
            Every screen below is the live product, shown on device — real screens, no staged renders.
          </p>
        </div>

        <ol className="flex flex-col gap-[var(--space-3xl)] md:gap-[var(--space-4xl)]">
          {STOPS.map((s, i) => {
            const flip = i % 2 === 1
            return (
              <li
                key={s.img}
                className="grid items-center gap-[var(--space-lg)] md:grid-cols-12 md:gap-[var(--space-2xl)]"
              >
                <figure className={`reveal md:col-span-5 ${flip ? 'md:order-2 md:col-start-8' : ''}`} style={{ ['--i' as string]: 0 }}>
                  <div className="border border-[var(--rule)] bg-[var(--paper-2)] p-3 md:p-5">
                    <div className="mx-auto aspect-[1000/750] w-full max-w-[460px]">
                      <img
                        src={s.img}
                        alt={s.alt}
                        width={1000}
                        height={750}
                        loading={i === 0 ? 'eager' : 'lazy'}
                        decoding="async"
                        className="block h-full w-full object-cover"
                        draggable={false}
                      />
                    </div>
                  </div>
                  <figcaption className="mt-[var(--space-sm)] flex items-center gap-[var(--space-xs)] font-mono text-[11px] tracking-[0.08em] text-[var(--muted)] uppercase">
                    <span className="inline-block h-2 w-2 bg-[var(--accent)]" aria-hidden />
                    Tour {String(i + 1).padStart(2, '0')} / {String(STOPS.length).padStart(2, '0')}
                  </figcaption>
                </figure>
                <div className={`reveal md:col-span-5 ${flip ? 'md:order-1 md:col-start-1' : 'md:col-start-7'}`} style={{ ['--i' as string]: 1 }}>
                  <h3 className="font-display text-[clamp(1.4rem,2.2vw,2rem)] leading-[1.05] font-bold tracking-[-0.015em] text-[var(--ink)]">
                    {s.title}
                  </h3>
                  <p className="mt-[var(--space-sm)] max-w-[42ch] text-[15px] leading-[1.75] text-[var(--muted)]">
                    {s.body}
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </section>
  )
}
