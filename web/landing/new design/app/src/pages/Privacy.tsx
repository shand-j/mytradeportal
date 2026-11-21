import { Link } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import { isPortalMode } from '../portal/host'
import { PortalShell } from '../portal/components/PortalShell'

export default function Privacy() {
  usePageMeta(
    'Privacy notice — My Trade Portal',
    'Privacy notice for My Trade Portal.',
  )

  const content = (
    <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Legal</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.5rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Privacy notice
      </h1>
      <div className="mt-[var(--space-md)] space-y-[var(--space-md)] text-[14.5px] leading-[1.75]">
        <p>
          This notice explains how My Trade Portal collects and uses personal
          information in the iOS app, back-office, customer portal and public
          quote and invoice pages.
        </p>

        <div>
          <h2 className="font-display text-lg font-extrabold uppercase">Data we process</h2>
          <p className="mt-2 text-[var(--muted)]">
            We process account and business details, customer and property details,
            quote and job descriptions, photos, messages, invoice records and
            payment metadata. Payment metadata may include the payer name,
            amount and invoice reference.
          </p>
        </div>

        <div>
          <h2 className="font-display text-lg font-extrabold uppercase">AI-assisted quotes</h2>
          <p className="mt-2 text-[var(--muted)]">
            Job descriptions and relevant photos may be sent to the configured
            OpenAI-compatible AI provider, currently Kimi/Moonshot, to draft
            guide-priced quotes and provide optional follow-up triage. Vision
            captions and quote text may contain personal or site information.
            Electricians review AI drafts and remain responsible for accuracy.
          </p>
        </div>

        <div>
          <h2 className="font-display text-lg font-extrabold uppercase">Analytics and payments</h2>
          <p className="mt-2 text-[var(--muted)]">
            We use product analytics to measure product reliability and feature
            use. Card payments are handled by Stripe Connect: Stripe-hosted
            payment fields receive card data, and platform servers never store
            or receive card numbers or security codes. Paddle subscription
            billing is disabled during beta.
          </p>
        </div>

        <div>
          <h2 className="font-display text-lg font-extrabold uppercase">Retention and access controls</h2>
          <p className="mt-2 text-[var(--muted)]">
            Records are retained only for their stated purpose and applicable
            legal period. UK financial records are retained for 6 years from
            the end of the relevant financial year; draft, declined or expired
            quotes are retained for 24 months.
            Offboarding immediately revokes access, deactivates accounts and
            anonymises personal data. Tenant isolation, role-based access and
            encrypted storage and transport are used to restrict access.
          </p>
        </div>

        <div>
          <h2 className="font-display text-lg font-extrabold uppercase">Your choices</h2>
          <p className="mt-2 text-[var(--muted)]">
            Subject to legal and accounting record requirements, you may request
            access to or correction of your information or ask the trade business
            that controls the record to erase it. Tenants can export their data
            and complete account offboarding from the back-office.
          </p>
        </div>
      </div>
      <p className="mt-[var(--space-lg)] text-[13.5px] text-[var(--muted)]">
        <Link to="/terms" className="link-arrow">Terms of Service</Link>
        {' · '}
        <Link to="/fair-use" className="link-arrow">Fair-use policy</Link>
      </p>
    </section>
  )

  if (isPortalMode()) {
    return <PortalShell>{content}</PortalShell>
  }

  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-start justify-center px-5 py-[var(--space-2xl)] md:py-[var(--space-3xl)]">
        <div className="w-full max-w-[720px]">{content}</div>
      </div>
      <Footer />
    </main>
  )
}
