import Logo from '../components/Logo'
import { TESTFLIGHT_URL } from '@/lib/site'

export default function Footer() {
  return (
    <footer className="bg-[var(--ink-deep)] text-[var(--paper-on-dark)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-2xl)] md:px-10">
        <div className="flex flex-wrap items-center justify-between gap-[var(--space-lg)]">
          <div className="flex items-center gap-[var(--space-sm)]">
            <Logo size={36} radius={0} className="shrink-0" />
            <div>
              <p className="font-display text-[clamp(1.3rem,2vw,1.75rem)] font-extrabold uppercase leading-none tracking-[0.04em]">
                MyTradePortal
              </p>
              <p className="mt-[var(--space-2xs)] text-[13px] text-[var(--paper-on-dark-muted)]">
                Built for the van. Not the desk.
              </p>
            </div>
          </div>
          <p className="text-[13.5px] text-[var(--paper-on-dark-muted)]">
            <a href="#features" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">The tour</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href="#pricing" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Pricing</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href="#reviews" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Reviews</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href="/blog" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Blog</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href="/help" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Help</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Join the beta</a>
            <span className="mx-[var(--space-sm)] text-[var(--rule-on-dark)]" aria-hidden>·</span>
            <a href="/fair-use" className="underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--paper-on-dark)] hover:underline">Fair use</a>
          </p>
        </div>
        <div className="mt-[var(--space-xl)] flex flex-wrap items-baseline justify-between gap-[var(--space-sm)] border-t border-[var(--rule-on-dark)] pt-[var(--space-lg)] text-[12px] text-[var(--paper-on-dark-muted)]">
          <span>© {new Date().getFullYear()} MyTradePortal Ltd · Leeds, United Kingdom</span>
          <span className="font-mono uppercase tracking-[0.18em]">iOS · Beta for electricians · Other trades to follow</span>
        </div>
      </div>
    </footer>
  )
}
