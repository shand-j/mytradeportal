import { Link } from 'react-router'
import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { usePageMeta } from '../hooks/usePageMeta'
import { isPortalMode } from '../portal/host'
import { PortalShell } from '../portal/components/PortalShell'

export default function Privacy() {
  usePageMeta(
    'Privacy notice — My Trade Portal',
    'How My Trade Portal processes AI prompts, analytics and payment metadata under UK GDPR.',
  )

  const content = (
    <section className="border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
      <p className="spec-label text-[var(--muted)]">Legal</p>
      <h1 className="mt-[var(--space-xs)] font-display text-[clamp(1.6rem,3.5vw,2.5rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
        Privacy notice
      </h1>
      <div className="mt-[var(--space-md)] space-y-6 text-[14.5px] leading-[1.75] text-[var(--muted)]">
        <p>
          <strong className="text-[var(--ink)]">Last updated: 20 November 2026.</strong>{' '}
          This notice explains how MyTradePortal Ltd (“My Trade Portal”, “we”, “us”) handles personal
          data when tradespeople, customers and visitors use the platform.
        </p>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Who controls your data
          </h2>
          <p className="mt-2">
            My Trade Portal acts as a data controller for platform accounts, security and service
            records. A trade business using My Trade Portal is the controller for the customer, quote,
            job and invoice records it submits. We process those records on the trade business’s
            instructions and under our agreement with it.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Data we process
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>Staff and customer identity, contact and account details.</li>
            <li>Site addresses, job descriptions, notes, dates, photos and communications.</li>
            <li>Quotes, line items, invoices, invoice references, amounts and payment status.</li>
            <li>Payment provider references and transaction metadata. We do not need or process card PAN values.</li>
            <li>Security, audit and product-analytics events, such as sign-up and first-quote milestones.</li>
          </ul>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            AI-assisted quote and follow-up processing
          </h2>
          <p className="mt-2">
            Prompts may contain customer personal data, including names, addresses, telephone numbers,
            free-text job descriptions and photo observations. We send the minimum job context needed
            to an approved OpenAI-compatible large-language-model provider to draft or refine a quote,
            answer a follow-up question or describe a photo. Electricians retain human review before
            a quote is sent.
          </p>
          <p className="mt-2">
            The AI provider acts on our instructions and processes prompt and response data only to
            provide the requested generation. We do not deliberately use tenant prompt data to train
            public platform models. AI-generated metadata is stored with the quote; AI output is
            guidance and may contain mistakes.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Product analytics
          </h2>
          <p className="mt-2">
            We record operational product events such as account activation, AI draft generation,
            quote sending and invoice milestones to improve reliability and understand product use.
            Events are tenant-scoped and may include tenant and actor identifiers plus the event
            properties needed for that measurement. Where configured, the same events may be sent to
            PostHog or an equivalent analytics processor. Analytics is not used to sell personal data.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Payments and PCI posture
          </h2>
          <p className="mt-2">
            Card payments use Stripe-hosted payment fields or Stripe checkout components. Cardholder
            PAN, CVV and full card data remain with Stripe; My Trade Portal never receives or stores
            those card details. We receive and store limited payment metadata — for example customer
            name, amount, invoice reference and Stripe or Paddle transaction references — for
            reconciliation, accounting, receipts, refunds and chargeback evidence.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Why we process data and UK GDPR bases
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><strong>Contract:</strong> provide accounts, quotes, jobs, invoices and payments.</li>
            <li><strong>Legal obligation:</strong> keep financial records and meet tax, security and audit duties.</li>
            <li><strong>Legitimate interests:</strong> prevent abuse, operate and improve the service, and investigate failures.</li>
            <li><strong>Consent:</strong> where a separate opt-in is requested, such as optional marketing.</li>
          </ul>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Retention
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><strong>Account and active operational records:</strong> kept while the tenant account is active and as needed to provide the service.</li>
            <li><strong>AI prompts and draft/declined/expired quotes:</strong> kept with quote records for up to 24 months, then deletable.</li>
            <li><strong>Accepted quotes and supporting invoice records:</strong> retained for 6 years from the end of the relevant financial year.</li>
            <li><strong>Invoices, invoice lines and payments:</strong> retained for 6 years for UK financial, VAT and dispute records.</li>
            <li><strong>Audit logs:</strong> retained for 6 years.</li>
            <li><strong>Product analytics:</strong> retained with the underlying tenant operational record or deleted/reduced in line with the data minimisation and offboarding process.</li>
            <li><strong>Backups:</strong> rotate within 35 days; offboarding anonymises the live database and restored copies must be re-anonymised before use.</li>
          </ul>
          <p className="mt-2">
            Retention is subject to longer hold periods where required for a legal claim, dispute,
            fraud investigation or statutory duty.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Subprocessors and access controls
          </h2>
          <p className="mt-2">
            We use hosting and infrastructure providers, an approved LLM provider, Stripe and, where
            enabled, Paddle or other communications and analytics providers. These processors receive
            only data needed for their service. International transfers are protected by the
            processor’s appropriate UK GDPR transfer mechanism.
          </p>
          <p className="mt-2">
            Access is role-based and tenant-isolated by database row-level security. Authentication,
            transport encryption, audit logging and least-privilege administration are applied.
            Staff data access is limited to personnel who need it to operate or support the platform.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Your choices and rights
          </h2>
          <p className="mt-2">
            You may ask for access, correction, restriction, objection, erasure or a copy of your
            personal data, where UK GDPR applies. Contact the trade business that holds the customer
            record; as the platform operator, we can also help route or fulfil a request.
          </p>
          <p className="mt-2">
            Marketing choices can be withdrawn at any time. A homeowner should first contact the trade
            business they dealt with. You may also complain to the UK Information Commissioner’s Office
            (ICO) if you believe your data has been handled improperly.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Offboarding and automated decisions
          </h2>
          <p className="mt-2">
            When a tenant leaves, staff and customer account details are revoked and anonymised or
            deleted according to the retention rules above. AI quotations are assistive and do not make
            legally significant decisions without electrician review. We do not use customer data for
            solely automated credit decisions or unrelated profiling.
          </p>
        </section>

        <section>
          <h2 className="font-display text-[1.15rem] font-extrabold uppercase text-[var(--ink)]">
            Contact and updates
          </h2>
          <p className="mt-2">
            Privacy or data-subject requests can be sent through the support or Help channel in the
            My Trade Portal app or website. We will update this notice when processing or legal
            requirements change and will show the updated date above.
          </p>
        </section>
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
