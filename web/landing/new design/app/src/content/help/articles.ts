export type HelpBlock =
  | { type: 'h2'; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  /**
   * Placeholder for a product screenshot. Rendered as a dashed frame; real
   * shots are captured later via scripts/capture-screenshots.mjs and swapped
   * in — keep labels stable so the capture script can match them.
   */
  | { type: 'shot'; label: string }

export type HelpAudience = 'electricians' | 'customers'

export interface HelpArticle {
  slug: string
  audience: HelpAudience
  title: string
  /** One-line summary shown on the index cards and used as meta description. */
  summary: string
  blocks: HelpBlock[]
}

export const AUDIENCES: { key: HelpAudience; title: string; blurb: string }[] = [
  {
    key: 'electricians',
    title: 'For electricians',
    blurb: 'Set up your business, send your first AI quote, and get paid — all from the app.',
  },
  {
    key: 'customers',
    title: 'For your customers',
    blurb: 'Homeowner guides: requesting quotes, accepting them, the portal, and paying online.',
  },
]

export const articles: HelpArticle[] = [
  // ── For electricians ────────────────────────────────────────────────
  {
    slug: 'getting-started',
    audience: 'electricians',
    title: 'Getting started: install, set up your business, choose a plan',
    summary:
      'From download to a fully set-up business in about fifteen minutes — onboarding, bank details, card payments and picking a plan.',
    blocks: [
      {
        type: 'p',
        text: 'My Trade Portal is an iPhone app for UK electricians: quotes, jobs, invoices and customer messages in one place. Install it from the link on our website (TestFlight while we’re in beta), open it and tap **Set up my business**.',
      },
      { type: 'shot', label: 'Onboarding welcome screen' },
      {
        type: 'p',
        text: 'The setup wizard walks you through twelve short steps. You can stop and come back — everything is saved:',
      },
      {
        type: 'ol',
        items: [
          '**Welcome** — a quick hello, nothing to fill in.',
          '**Account** — your name, email and password. This is your login.',
          '**Identity** — your trading name, as customers will see it.',
          '**Address** — your business address and the area you cover.',
          '**Tax** — VAT registration if you have it (skip if you don’t).',
          '**Compliance** — your competent-person scheme (NICEIC, NAPIT and so on), if you’re registered.',
          '**Services** — the work you take on, so quote requests are triaged properly.',
          '**Branding** — your colour and logo (you can skip and do it later).',
          '**Review** — check everything, then launch. Your business is created here.',
          '**Bank details** — sort code and account number. These print on every invoice so customers can pay by bank transfer.',
          '**Card payments** — “Will you take card payments?” Say yes to connect Stripe now (takes a few minutes, in the app), or **Not now** and do it later from **Settings → Payments**.',
          '**Plan** — pick a plan and start your 14-day free trial.',
        ],
      },
      {
        type: 'h2',
        text: 'Choosing a plan',
      },
      {
        type: 'p',
        text: 'Every plan is one flat price per business with AI included — no credits, no counting. The only difference is how many staff seats you get:',
      },
      {
        type: 'ul',
        items: [
          '**Sole Trader — £25/month** (£250/year): just you, 1 seat.',
          '**Pro — £39/month** (£390/year): growing businesses, up to 5 seats.',
          '**Team — £69/month** (£690/year): multi-engineer teams, up to 15 seats.',
        ],
      },
      {
        type: 'p',
        text: 'All plans start with a **14-day free trial**, and you can change or cancel any time from **Settings → Subscription → Manage subscription**. The card you pay with at the end of onboarding is handled by our billing partner, Paddle — we never see your card number.',
      },
    ],
  },
  {
    slug: 'first-ai-quote',
    audience: 'electricians',
    title: 'Your first AI quote',
    summary:
      'Describe the job in plain English, let the AI draft guide-priced line items, then review, refine and send — all in minutes.',
    blocks: [
      {
        type: 'p',
        text: 'From the dashboard or a lead, tap **New quote**. The intake asks what you’d note down anyway: the customer, property type, where the consumer unit is, parking and access, photos — and a plain-English description of the job, exactly as you’d tell a mate.',
      },
      { type: 'shot', label: 'Quote intake screen with job description' },
      {
        type: 'p',
        text: 'Tap generate and the AI drafts the quote: labour and materials as guide-priced, ex-VAT line items, matched against a UK parts catalogue. It’s a first draft, not gospel — **every line is editable** before anything reaches the customer.',
      },
      {
        type: 'h2',
        text: 'Review, then refine',
      },
      {
        type: 'p',
        text: 'Check the lines, tweak prices, add or delete anything. If the draft is broadly right but not quite, use **Refine**: type an instruction like “add two more sockets in the kitchen” or “swap to a metal-clad board” and the AI regenerates its lines — anything you added or edited by hand is left untouched.',
      },
      { type: 'shot', label: 'Quote editor with refine box' },
      {
        type: 'p',
        text: 'Happy with it? Tap **Send quote**. Your customer gets an email with a secure link to view, accept or decline online — no PDF attachments lost in spam. You’ll see when it’s accepted, and you can turn it into a job with one tap.',
      },
      {
        type: 'ul',
        items: [
          'AI prices are **guide prices** — sense-check them against your merchant before sending.',
          'The AI can’t make technical judgement calls. Design, testing and certification decisions stay with you.',
          'Sent quotes lock against editing, so what your customer sees never changes under them.',
        ],
      },
    ],
  },
  {
    slug: 'customers-and-crm',
    audience: 'electricians',
    title: 'Customers & the CRM',
    summary:
      'Every customer, property and quote request in one list — and how new enquiries land in your inbox automatically.',
    blocks: [
      {
        type: 'p',
        text: 'The **Customers** tab is your CRM: every contact with their property details, parking and access notes, and full history — quote requests, quotes, jobs and invoices. When you start a quote for a returning customer, their property details pre-fill the intake.',
      },
      { type: 'shot', label: 'Customers list and customer detail' },
      {
        type: 'h2',
        text: 'Where new enquiries come from',
      },
      {
        type: 'ul',
        items: [
          '**Your 6-digit customer code** — share it (Settings has a share button) and customers can find your business in the app and send you a quote request.',
          '**Your customer portal** — every business gets a branded portal page where homeowners can request a quote and track their documents.',
          '**Add manually** — met someone on site? Add the lead yourself in a few taps.',
        ],
      },
      {
        type: 'p',
        text: 'New requests land in your inbox with the customer’s answers, photos and an AI triage of urgency. From there it’s one tap into the quote intake — no retyping.',
      },
    ],
  },
  {
    slug: 'jobs-and-calendar',
    audience: 'electricians',
    title: 'Jobs & the calendar',
    summary:
      'Turn accepted quotes into scheduled jobs, see your week at a glance, and let the app stop double-bookings before they happen.',
    blocks: [
      {
        type: 'p',
        text: 'When a customer accepts a quote, tap **Convert to job** (or create a job from scratch). Pick a start date — the app suggests the earliest slot where the whole job fits around your existing bookings.',
      },
      {
        type: 'h2',
        text: 'Multi-day jobs',
      },
      {
        type: 'p',
        text: 'If a job needs more hours than a working day, day one is capped and the rest is booked as consecutive working-day blocks automatically. Reschedule the job and every block moves with it — no re-planning by hand. Your working days and hours come from **Settings → Working hours**.',
      },
      { type: 'shot', label: 'Calendar week view with scheduled jobs' },
      {
        type: 'h2',
        text: 'All / Me',
      },
      {
        type: 'p',
        text: 'On multi-seat plans the calendar has an **All / Me** filter: All shows everyone’s jobs, Me narrows to the jobs assigned to you. Single-seat plans don’t need it, so it stays hidden.',
      },
      {
        type: 'h2',
        text: 'The guardrails, in plain language',
      },
      {
        type: 'ul',
        items: [
          '**No double-booking.** You can’t schedule two things for the same engineer at overlapping times — the app says what clashes instead of letting you find out on the day.',
          '**The 10-hour day cap.** Nobody gets more than 10 hours booked in a day. Longer work spills into the next working day.',
          '**Locked jobs.** Once a job is in progress or completed, its dates can’t be moved — the record of what actually happened stays intact.',
        ],
      },
      {
        type: 'p',
        text: 'Want your jobs in Apple or Google Calendar? **Settings → Calendar subscription** adds a live feed, so booked jobs appear in your normal calendar app too.',
      },
    ],
  },
  {
    slug: 'invoices-and-getting-paid',
    audience: 'electricians',
    title: 'Invoices & getting paid',
    summary:
      'Send invoices that mirror the accepted quote, let customers pay by card or bank transfer, and get Stripe payouts to your bank.',
    blocks: [
      {
        type: 'p',
        text: 'Create an invoice from an accepted quote or a finished job and it **mirrors the quote’s totals exactly** — no re-adding, no surprises for the customer. You can also raise a scratch invoice for anything else.',
      },
      { type: 'shot', label: 'Invoice detail with send and mark-paid actions' },
      {
        type: 'h2',
        text: 'Two ways to be paid',
      },
      {
        type: 'ul',
        items: [
          '**Bank transfer** — works from day one. Your sort code and account number (from onboarding, or **Settings → Payment details**) print on every invoice. When the money lands, tap **Mark paid**.',
          '**Card** — connect Stripe from **Settings → Payments** and every invoice email includes a secure **pay by card** link. Customers pay in a couple of taps on any device.',
        ],
      },
      {
        type: 'h2',
        text: 'Where the card money goes',
      },
      {
        type: 'p',
        text: 'Card payments go into your own Stripe account and pay out to your bank automatically on Stripe’s normal schedule (typically a few working days). Stripe’s card processing fees come out of the payment; we don’t take a cut of your invoices.',
      },
      {
        type: 'p',
        text: 'Overdue invoice? The app sends polite reminders for you until it’s paid — you set the rhythm in **Settings → Follow-up settings**. Every send is logged, so you always know what the customer has been told.',
      },
    ],
  },
  {
    slug: 'team-and-invites',
    audience: 'electricians',
    title: 'Team: invites & seats',
    summary:
      'Invite office staff and engineers, choose their role, and understand how seats work on each plan.',
    blocks: [
      {
        type: 'p',
        text: 'Go to **Settings → Team**, enter their name and email, pick a role and send the invite. They get an email with a link to set their password, then log in on their own phone.',
      },
      { type: 'shot', label: 'Team settings with pending invite' },
      {
        type: 'h2',
        text: 'Seats by plan',
      },
      {
        type: 'ul',
        items: [
          '**Sole Trader** — 1 seat (just you).',
          '**Pro** — up to 5 seats.',
          '**Team** — up to 15 seats.',
        ],
      },
      {
        type: 'p',
        text: '**Pending invites count toward your seats** until they’re accepted, so a full plan can’t hold open invitations. If you hit the limit the app tells you and offers the cheapest upgrade with more seats — change plans any time from **Settings → Subscription**.',
      },
      {
        type: 'p',
        text: 'Everyone on your team shares the same customers, quotes and calendar — use the calendar’s **All / Me** filter to see who’s doing what.',
      },
    ],
  },
  {
    slug: 'branding',
    audience: 'electricians',
    title: 'Branding: colour, logo & your portal',
    summary:
      'Make every quote, invoice and your customer portal look like your business, not ours.',
    blocks: [
      {
        type: 'p',
        text: 'Open **Settings → Business profile & branding**. Upload your logo and pick your brand colour — that’s genuinely all there is to it.',
      },
      { type: 'shot', label: 'Branding settings with colour picker and logo' },
      {
        type: 'p',
        text: 'Your branding flows through to everything your customer touches:',
      },
      {
        type: 'ul',
        items: [
          'Quote and invoice documents',
          'The emails they receive',
          '**Your customer portal** — your own branded page where homeowners request quotes, accept them and pay invoices',
        ],
      },
      {
        type: 'p',
        text: 'Changed your branding? It applies to everything new straight away — documents already sent keep the look they were sent with.',
      },
    ],
  },
  {
    slug: 'notifications-and-reminders',
    audience: 'electricians',
    title: 'Notifications & automatic reminders',
    summary:
      'What the app tells you, what it chases for you, and how to tune the follow-ups.',
    blocks: [
      {
        type: 'p',
        text: 'You get a push notification when something needs you: a new quote request, a quote accepted or declined, a payment landing. Emails cover the paper trail — quotes and invoices you send, and copies of what customers receive.',
      },
      {
        type: 'h2',
        text: 'The automatic chasing',
      },
      {
        type: 'ul',
        items: [
          '**Quote reminders** — a quote that goes quiet is nudged up to 3 times by email, then the app stops (nobody likes being hounded).',
          '**Invoice reminders** — overdue invoices are chased until they’re paid.',
          '**Appointment reminders** — customers get an SMS before a booked visit; they can reply STOP to opt out of texts.',
        ],
      },
      { type: 'shot', label: 'Follow-up settings screen' },
      {
        type: 'p',
        text: 'Tune the rhythm — or turn reminders off entirely — in **Settings → Follow-up settings**. You can switch quote and invoice reminders on or off separately, change how many quote reminders go out, and set the gap in days between them. Every send is logged against the quote or invoice so you can see exactly what’s gone out.',
      },
      {
        type: 'p',
        text: 'One more setting lives there: **total rounding**, which rounds your quote totals up to the nearest £5 or £10 if you like cleaner numbers.',
      },
    ],
  },
  {
    slug: 'faq',
    audience: 'electricians',
    title: 'Frequently asked questions',
    summary: 'The short answers to the things every new user asks.',
    blocks: [
      {
        type: 'h2',
        text: 'Is the AI really included, or is it metered?',
      },
      {
        type: 'p',
        text: 'Included on every plan, unmetered. No credits, no allowances, no per-quote charges. A fair-use policy applies to abuse, not to normal busy weeks.',
      },
      {
        type: 'h2',
        text: 'Do I have to take card payments?',
      },
      {
        type: 'p',
        text: 'No. Bank transfer works from day one with the details from onboarding. Card payments via Stripe are optional — turn them on any time from **Settings → Payments**.',
      },
      {
        type: 'h2',
        text: 'Can I edit what the AI writes?',
      },
      {
        type: 'p',
        text: 'Yes — everything. Lines, prices, descriptions, the lot, before anything is sent. Once a quote is sent it locks, so the customer always sees exactly what you sent.',
      },
      {
        type: 'h2',
        text: 'What happens when my free trial ends?',
      },
      {
        type: 'p',
        text: 'Your chosen plan starts and the card from onboarding is billed by Paddle, our billing partner. Cancel before the trial ends from **Settings → Subscription → Manage subscription** and you pay nothing — your data stays put either way.',
      },
      {
        type: 'h2',
        text: 'Can I change plans later?',
      },
      {
        type: 'p',
        text: 'Any time, from the same subscription screen. Upgrades apply straight away; downgrades take effect at the next renewal.',
      },
      {
        type: 'h2',
        text: 'Is there an Android version?',
      },
      {
        type: 'p',
        text: 'Not yet — we’re iPhone-first while we’re in beta. Your customers don’t need any app at all: quotes, the portal and card payments all work in their web browser.',
      },
      {
        type: 'h2',
        text: 'Who sees my customer data?',
      },
      {
        type: 'p',
        text: 'Your business’s data is yours — each business on My Trade Portal is walled off from every other at the database level. We never sell data, and AI quote drafting sends job descriptions, not your customer list.',
      },
    ],
  },

  // ── For your customers (homeowners) ─────────────────────────────────
  {
    slug: 'requesting-a-quote',
    audience: 'customers',
    title: 'Requesting a quote',
    summary:
      'How to ask your electrician for a quote — from their portal, their code, or a link they send you.',
    blocks: [
      {
        type: 'p',
        text: 'You can request a quote from your electrician’s own portal page (they’ll share the link or a QR code), or in the My Trade Portal app using the **6-digit code** they give you. You don’t need to create an account first.',
      },
      { type: 'shot', label: 'Quote request form, job type step' },
      {
        type: 'p',
        text: 'The form is short and asks for what your electrician actually needs:',
      },
      {
        type: 'ul',
        items: [
          'Your postcode and contact details',
          'A bit about the property (house or flat, bedrooms)',
          'The type of job — a few quick questions specific to the work',
          'Photos, if you have them (a picture of the consumer unit saves a lot of back-and-forth)',
          'How soon you need it done, and a rough budget if you have one',
        ],
      },
      {
        type: 'p',
        text: 'When you submit, an instant check flags anything that looks urgent (like a burning smell or a dead consumer unit) so your electrician sees it right away. You’ll get a confirmation, and the quote itself arrives by email — usually far quicker than waiting for someone to call back.',
      },
    ],
  },
  {
    slug: 'reviewing-your-quote',
    audience: 'customers',
    title: 'Viewing, accepting or declining your quote',
    summary:
      'Open the link in your email, check the breakdown, then accept (and pick dates that suit you), decline, or ask a question.',
    blocks: [
      {
        type: 'p',
        text: 'When your electrician sends your quote, you get an email with a secure link. Tap it to see the full breakdown — every line of labour and materials, the total, and how long the work should take. Nothing to download, nothing to install.',
      },
      { type: 'shot', label: 'Quote page with accept and decline buttons' },
      {
        type: 'h2',
        text: 'Your three options',
      },
      {
        type: 'ul',
        items: [
          '**Accept** — happy with the quote? Accept it online. You can then pick **up to 3 preferred visit dates** from a calendar that shows when your electrician is actually free, so the booking conversation starts from real availability.',
          '**Decline** — not for you? Decline with a tap (a reason is optional but helps). No awkward phone call needed.',
          '**Ask first** — unsure about something? Reply to the quote email or message your electrician to talk it through before deciding.',
        ],
      },
      {
        type: 'p',
        text: 'Changed your mind after declining? Just reply to the email or contact your electrician — they can send a fresh quote.',
      },
      {
        type: 'p',
        text: 'After you accept, your electrician confirms the date and you’ll get a reminder before the visit.',
      },
    ],
  },
  {
    slug: 'customer-portal',
    audience: 'customers',
    title: 'Your customer portal',
    summary:
      'One branded page from your electrician where your quotes, bookings and invoices all live.',
    blocks: [
      {
        type: 'p',
        text: 'Every electrician on My Trade Portal has their own portal — a page with their branding, just for their customers. It’s where you can request a quote, see every quote and invoice they’ve sent you, and check your bookings.',
      },
      { type: 'shot', label: 'Customer portal home' },
      {
        type: 'h2',
        text: 'Signing in (there’s no password to remember)',
      },
      {
        type: 'p',
        text: 'The portal uses **magic-link sign in**: enter your email address and we email you a one-time link that signs you in. No password, no account setup, nothing to forget. The link only goes to your email, so only you can see your documents.',
      },
      {
        type: 'p',
        text: 'Inside you’ll find:',
      },
      {
        type: 'ul',
        items: [
          '**Quotes** — view, accept or decline, and pick preferred visit dates',
          '**Invoices** — see what’s outstanding and pay by card',
          '**Bookings** — what’s scheduled and when',
        ],
      },
      {
        type: 'p',
        text: 'Bookmark the page — it’s the quickest way back to anything your electrician has sent you.',
      },
    ],
  },
  {
    slug: 'paying-an-invoice',
    audience: 'customers',
    title: 'Paying an invoice by card',
    summary:
      'Tap the link in your invoice email and pay securely by card in a couple of minutes.',
    blocks: [
      {
        type: 'p',
        text: 'When your electrician sends an invoice, the email includes a **Pay now** link. Tap it, check the amount matches the invoice, and pay by card — Visa, Mastercard and the other usual cards all work.',
      },
      { type: 'shot', label: 'Secure card payment page' },
      {
        type: 'p',
        text: 'Payment is handled by **Stripe**, the same payment company used by millions of businesses. Your card details go straight to Stripe — your electrician never sees or stores them, and neither do we.',
      },
      {
        type: 'ul',
        items: [
          'You’ll see a confirmation on screen as soon as the payment goes through.',
          'The invoice updates to **Paid**, and your electrician is notified automatically.',
          'Prefer bank transfer? The invoice shows your electrician’s bank details too — pay either way.',
        ],
      },
      {
        type: 'p',
        text: 'If the payment page ever says the link has expired or the invoice is already paid, just contact your electrician — they can send a fresh link or confirm what’s happened.',
      },
    ],
  },
  {
    slug: 'reminders-and-messages',
    audience: 'customers',
    title: 'Reminders & staying in the loop',
    summary:
      'What we email and text you, and how to opt out of texts with one word.',
    blocks: [
      {
        type: 'p',
        text: 'You’ll hear from us at the moments that matter — never for marketing unless you asked for it:',
      },
      {
        type: 'ul',
        items: [
          '**Email** when a quote or invoice arrives, and a gentle nudge if a quote sits unanswered',
          '**Email** confirmation when you accept a quote or pay an invoice',
          '**Text message (SMS)** before a booked visit, so the appointment doesn’t sneak up on you',
        ],
      },
      {
        type: 'h2',
        text: 'Opting out of texts',
      },
      {
        type: 'p',
        text: 'Reply **STOP** to any reminder text and we won’t text you again — emails still arrive as normal, so you won’t miss anything important. Changed your mind? Reply **START** or **UNSTOP** and texts resume.',
      },
      {
        type: 'p',
        text: 'You can also tell your electrician how you prefer to be contacted — phone, email, text or in-app chat — and update your details any time from your profile in the app.',
      },
    ],
  },
]

export const getArticleBySlug = (slug: string): HelpArticle | undefined =>
  articles.find((a) => a.slug === slug)

export const articlesFor = (audience: HelpAudience): HelpArticle[] =>
  articles.filter((a) => a.audience === audience)
