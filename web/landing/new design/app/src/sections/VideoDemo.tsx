import { useEffect, useRef } from 'react'

const SIDES = [
  {
    video: '/assets/customer.mp4',
    label: 'Recording 01 — customer side',
    title: 'They request. In two minutes.',
    body: 'Your customer enters your code, describes the job, picks a day — and it lands in your leads with photos, not a vague text. Track quotes and appointments without a single phone call.',
    points: ['Property profile & photos up front', 'Picks from your real availability', 'Tracks quotes and bookings in one place'],
  },
  {
    video: '/assets/electrician.mp4',
    label: 'Recording 02 — your side',
    title: 'You approve. From the van.',
    body: 'Leads arrive with an estimate attached. The AI drafts the quote — line items, VAT, confidence score — you tweak the numbers, tap update, done. Chat, calendar and job sheets live behind the same login.',
    points: ['AI-drafted quotes you approve', 'Quick-request chat, not phone tag', 'Job sheet with access notes on the day'],
  },
]

export default function VideoDemo() {
  const root = useRef<HTMLElement>(null)

  useEffect(() => {
    /* Play videos only while on screen */
    const videos = root.current?.querySelectorAll('video') ?? []
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          const v = e.target as HTMLVideoElement
          if (e.isIntersecting) v.play().catch(() => {})
          else v.pause()
        })
      },
      { threshold: 0.25 },
    )
    videos.forEach((v) => io.observe(v))
    return () => io.disconnect()
  }, [])

  return (
    <section ref={root} className="border-b-2 border-[var(--ink)] bg-[var(--ink)] text-[var(--paper-on-dark)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-3xl)] max-w-[46ch]">
          <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em]">
            One job, both sides of the app.
          </h2>
          <p className="reveal mt-[var(--space-md)] text-[15.5px] leading-[1.75] text-[var(--paper-on-dark-muted)]" style={{ ['--i' as string]: 1 }}>
            Real screen recordings from the native iOS app, start to finish. No actors, no mock-ups.
          </p>
        </div>

        <div className="grid gap-[var(--space-3xl)] md:grid-cols-2 md:gap-[var(--space-2xl)]">
          {SIDES.map((s) => (
            <div key={s.label}>
              <figure className="reveal" style={{ ['--i' as string]: 0 }}>
                <div className="border border-[var(--rule-on-dark)] bg-[var(--ink-pressed)] p-3">
                  <div className="mx-auto aspect-[368/800] w-full max-w-[239px]">
                    <video
                      src={s.video}
                      muted
                      loop
                      playsInline
                      preload="metadata"
                      width={368}
                      height={800}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                </div>
                <figcaption className="mt-[var(--space-sm)] flex items-center gap-[var(--space-xs)] font-mono text-[11px] tracking-[0.08em] text-[var(--paper-on-dark-muted)] uppercase">
                  <span className="inline-block h-2 w-2 bg-[var(--accent)]" aria-hidden />
                  {s.label}
                </figcaption>
              </figure>
              <div className="reveal mt-[var(--space-lg)]" style={{ ['--i' as string]: 1 }}>
                <h3 className="font-display text-[clamp(1.4rem,2.2vw,2rem)] leading-[1.05] font-bold tracking-[-0.015em]">
                  {s.title}
                </h3>
                <p className="mt-[var(--space-sm)] max-w-[44ch] text-[15px] leading-[1.75] text-[var(--paper-on-dark-muted)]">
                  {s.body}
                </p>
                <ul className="mt-[var(--space-md)] space-y-[var(--space-xs)]">
                  {s.points.map((pt) => (
                    <li key={pt} className="flex items-baseline gap-[var(--space-sm)] text-[14px] text-[var(--paper-on-dark)]">
                      <span className="inline-block h-[3px] w-5 shrink-0 translate-y-[-3px] bg-[var(--accent)]" aria-hidden />
                      {pt}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
