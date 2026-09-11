const STEPS = [
  {
    n: '1.0',
    title: 'Create account',
    body: 'Choose your plan and create your account in the app. No paperwork, no tech jargon.',
  },
  {
    n: '2.0',
    title: 'Onboard your business',
    body: 'Guided setup: your details, logo, brand colour, services and qualifications. Done in a couple of minutes.',
  },
  {
    n: '3.0',
    title: 'Share your code',
    body: 'You get a 6-digit code. Customers enter it in the app and see your business, not ours.',
  },
]

export default function HowItWorks() {
  return (
    <section id="how" className="border-b-2 border-[var(--ink)] bg-[var(--paper-2)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-3xl)] grid gap-[var(--space-lg)] md:grid-cols-12">
          <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em] text-[var(--ink)] md:col-span-7">
            Up and running in 2 minutes.
          </h2>
          <p className="reveal max-w-[38ch] self-end text-[15.5px] leading-[1.75] text-[var(--muted)] md:col-span-4 md:col-start-9" style={{ ['--i' as string]: 1 }}>
            No coding. No developer accounts. No waiting on us — create account,
            onboard your business, share your code, and you're taking quotes.
          </p>
        </div>

        <ol className="grid gap-[var(--space-xl)] md:grid-cols-3 md:gap-[var(--space-lg)]">
          {STEPS.map((s, i) => (
            <li
              key={s.n}
              className="reveal border-t-2 border-[var(--ink)] pt-[var(--space-md)]"
              style={{ ['--i' as string]: i }}
            >
              <p className="font-mono text-[13px] font-medium tracking-[0.14em] text-[var(--accent-dark)]">{s.n}</p>
              <h3 className="mt-[var(--space-sm)] font-display text-[clamp(1.3rem,1.9vw,1.75rem)] leading-[1.1] font-bold tracking-[-0.01em] text-[var(--ink)]">
                {s.title}
              </h3>
              <p className="mt-[var(--space-sm)] max-w-[36ch] text-[14.5px] leading-[1.75] text-[var(--muted)]">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}
