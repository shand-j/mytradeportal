import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { usePageMeta } from '../hooks/usePageMeta'

/**
 * Only the app's own custom scheme may be bounced to. Anything else (http,
 * javascript:, data:, …) is ignored so this page can never be abused as an
 * open redirect.
 */
const ALLOWED_SCHEMES = ['mtp:']

function bounceTarget(next: string | null): string | null {
  if (!next) return null
  try {
    const scheme = new URL(next).protocol.toLowerCase()
    return ALLOWED_SCHEMES.includes(scheme) ? next : null
  } catch {
    return null
  }
}

/**
 * Stripe Connect onboarding bounce. Stripe's AccountLink API only accepts
 * http(s) return/refresh URLs, but the mobile app needs to end up back inside
 * itself — so the API hands Stripe this https page with the app's deep link
 * (mtp://…) encoded in `next`. We immediately navigate to it; the in-app
 * auth-session browser (expo-web-browser openAuthSessionAsync) intercepts
 * that navigation and closes, returning the tradie to the app. The link is
 * the manual fallback if the interception never happens.
 */
export default function StripeBounce() {
  usePageMeta(
    'Returning to the app — My Trade Portal',
    'Finishing your card payments setup and returning you to the My Trade Portal app.',
  )

  const [searchParams] = useSearchParams()
  const target = useMemo(() => bounceTarget(searchParams.get('next')), [searchParams])

  useEffect(() => {
    if (target) {
      window.location.href = target
    }
  }, [target])

  return (
    <main className="relative flex min-h-screen flex-col">
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        <section className="w-full max-w-[480px] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 text-center md:p-10">
          <p className="spec-label text-[var(--muted)]">Card payments setup</p>
          <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.4rem,3vw,2rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
            Returning to the app…
          </h1>
          {target ? (
            <p className="mt-[var(--space-md)] text-[14.5px] leading-[1.75] text-[var(--muted)]">
              Taking you back to the My Trade Portal app to finish setting up
              card payments. If nothing happens,{' '}
              <a
                href={target}
                className="font-semibold text-[var(--ink)] underline underline-offset-4"
              >
                tap here to open the app
              </a>
              .
            </p>
          ) : (
            <p className="mt-[var(--space-md)] text-[14.5px] leading-[1.75] text-[var(--muted)]">
              This link isn&apos;t valid. Open the My Trade Portal app and
              restart your card payments setup from Settings.
            </p>
          )}
        </section>
      </div>
    </main>
  )
}
