import HandUnderline from '../components/HandUnderline'
import { TESTFLIGHT_URL } from '@/lib/site'

export default function Hero() {
  return (
    <section id="top" className="border-b-2 border-[var(--ink)]">
      <div className="mx-auto grid max-w-[1600px] items-center gap-10 px-6 pb-14 pt-14 md:grid-cols-[1fr_1.35fr] md:gap-14 md:px-10 md:pb-20 md:pt-20">
        {/* Copy */}
        <div>
          <h1 className="reveal font-display text-[clamp(2.9rem,5.8vw,5.6rem)] font-extrabold leading-[0.95] tracking-[-0.02em]" style={{ ['--i' as string]: 0 }}>
            Your trade.
            <br />
            <span className="relative inline-block">
              Your own
              <HandUnderline className="absolute -bottom-2 left-0 h-[0.14em] w-full" />
            </span>
            <br />
            app.
          </h1>
          <p className="reveal mt-7 max-w-md text-[16.5px] leading-relaxed text-[var(--muted)]" style={{ ['--i' as string]: 1 }}>
            Built for electricians, native on iOS. Your customers download the app and it puts
            on your brand the moment they sign in — quotes, bookings, reviews and invoices,
            live in <b className="font-semibold text-[var(--ink)]">48 hours</b>.
          </p>
          <div className="reveal mt-8 flex flex-wrap items-center gap-x-6 gap-y-4" style={{ ['--i' as string]: 2 }}>
            <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="chip chip--fill">
              Join the beta →
            </a>
            <a href="#features" className="link-arrow">
              Take the tour
            </a>
          </div>
          <p className="reveal spec-label mt-9 border-t border-[var(--rule)] pt-4 text-[var(--muted)]" style={{ ['--i' as string]: 3 }}>
            Now in beta for electricians · Other trades after beta · Android to follow
          </p>
        </div>

        {/* Real product footage, clipped by the viewport edge */}
        <figure className="reveal md:mr-[calc((100vw-100%)/-2)]" style={{ ['--i' as string]: 2 }}>
          <div className="border border-[var(--rule)] bg-[var(--ink)]">
            <video
              src="/assets/customer.mp4"
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              {...({ fetchpriority: 'high' } as Record<string, string>)}
              className="aspect-[16/10] w-full object-cover object-top"
            />
          </div>
          <figcaption className="spec-label mt-3 flex items-center gap-2 text-[var(--muted)]">
            <span className="inline-block h-2 w-2 bg-[var(--accent)]" aria-hidden />
            Live build — a customer requests a consumer-unit upgrade, start to finish
          </figcaption>
        </figure>
      </div>
    </section>
  )
}
