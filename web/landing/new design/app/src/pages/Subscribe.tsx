import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { SubscribePanel } from '../subscribe/SubscribePanel'
import { useFeatureFlags } from '@/lib/feature-flags'

export default function Subscribe() {
  const { paddleBilling } = useFeatureFlags()
  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        {paddleBilling ? (
          <SubscribePanel />
        ) : (
          <section className="mx-auto w-full max-w-[560px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
            <p className="spec-label text-[var(--muted)]">Free beta</p>
            <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.25rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
              Billing is paused for beta
            </h1>
            <p className="mt-[var(--space-sm)] text-[14px] leading-relaxed text-[var(--muted)]">
              You don&apos;t need to subscribe right now — invited beta businesses keep full
              access for free while we validate readiness.
            </p>
          </section>
        )}
      </div>
      <Footer />
    </main>
  )
}
