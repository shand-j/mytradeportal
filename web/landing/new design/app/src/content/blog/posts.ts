export type Block =
  | { type: 'h2'; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'quote'; text: string; cite?: string }

export interface BlogPost {
  slug: string
  title: string
  /** ISO publish date */
  date: string
  readMinutes: number
  excerpt: string
  /** Meta description for the article page */
  description: string
  blocks: Block[]
}

export const posts: BlogPost[] = [
  {
    slug: 'ai-in-the-trades',
    title: 'AI in the trades: what it can (and can’t) do for electricians in 2026',
    date: '2026-09-08',
    readMinutes: 6,
    excerpt:
      'Beyond the hype: where AI genuinely helps a UK electrician today — quote drafting, parts pricing, customer comms — and the lines it should never cross.',
    description:
      'A practical, non-hype look at what AI can and can’t do for UK electricians in 2026: quote drafting, parts pricing, customer comms, and where the limits are.',
    blocks: [
      {
        type: 'p',
        text: 'If you’ve spent any time on LinkedIn or trade forums lately, you’d think AI is about to rewire your consumer units for you. It isn’t. But dismissing it entirely is just as silly, because a few genuinely useful things have quietly become reliable — and they happen to be the things most electricians lose their evenings to.',
      },
      {
        type: 'p',
        text: 'Here’s an honest tour of what AI is good at on site and in the office, what it still gets wrong, and where the line should be.',
      },
      {
        type: 'h2',
        text: 'What it’s genuinely good at',
      },
      {
        type: 'p',
        text: '**Turning a job description into a first-draft quote.** This is the strongest use case by a mile. You describe the job in plain English — “replace consumer unit, add two double sockets in the kitchen, test and certify” — and a well-built tool turns that into a structured list of labour lines and materials, priced from a parts catalogue. You still check every line, but you’re editing instead of starting from a blank page. That difference matters at 9pm.',
      },
      {
        type: 'p',
        text: '**Parts pricing and descriptions.** AI is good at matching “that grey 2-gang switched socket” to the actual product, complete with the right terminology for the paperwork. It won’t know what’s in your van or what your merchant has in stock — but it stops you typing the same product descriptions for the hundredth time.',
      },
      {
        type: 'p',
        text: '**Customer comms.** Polite chasing messages, “running 20 minutes late” texts, follow-ups after a quote goes quiet. AI drafts these in your tone from a one-line instruction, and they’re almost always fine to send as-is. The value isn’t the writing — it’s that the message actually goes out, instead of sitting in your head while you’re up a ladder.',
      },
      {
        type: 'ul',
        items: [
          'Drafting a structured quote from a voice-note-style job description',
          'Rewriting rough notes into clean wording for quotes and invoices',
          'Drafting polite chase messages for unpaid or unaccepted quotes',
          'Summarising a long email thread from a letting agent into “what they actually want”',
          'Turning job photos plus a description into a checklist for a rewire quote',
        ],
      },
      {
        type: 'h2',
        text: 'Where it falls over',
      },
      {
        type: 'p',
        text: '**Regulations and compliance.** AI does not know BS 7671, the 18th Edition, or Part P — not reliably enough to bet your registration on. It can produce something that *sounds* like a competent designer wrote it, with confident references that are wrong or out of date. Every technical decision, every circuit calculation, every certification statement is yours. Full stop.',
      },
      {
        type: 'p',
        text: '**Prices.** AI will happily invent a parts price that hasn’t been true since 2022. Any tool you use should be grounding its figures in a real, current catalogue — and you should still spot-check against your own merchant. A quote built on hallucinated prices isn’t a quote; it’s a liability.',
      },
      {
        type: 'p',
        text: '**Judgement calls.** “Can this board be extended or does it need replacing?” “Is that cable run acceptable?” AI has no liability insurance and no hands. It can list the considerations; it cannot make the call.',
      },
      {
        type: 'h2',
        text: 'How to adopt it without the pain',
      },
      {
        type: 'p',
        text: 'Start with the boring stuff. Let AI draft the messages and the first pass of the quote, and keep your expertise where it legally has to be: the design, the testing, the certification, the final price you’re prepared to stand behind. The electricians getting value from AI in 2026 aren’t using it to replace their judgement — they’re using it to get their evenings back.',
      },
      {
        type: 'quote',
        text: 'The tool should do the typing. You still do the thinking.',
        cite: 'Worth pinning above the desk',
      },
      {
        type: 'p',
        text: 'That division of labour — machine drafts, human decides — is exactly how we’ve built the quote engine in My Trade Portal. AI proposes the line items from your description, grounded in a UK parts catalogue, and every line is editable before it reaches the customer. If a tool you’re evaluating doesn’t let you override its output, walk away.',
      },
    ],
  },
  {
    slug: 'time-saved-with-ai',
    title: 'How much time can AI really save a tradesperson?',
    date: '2026-09-09',
    readMinutes: 5,
    excerpt:
      'We work through a real Tuesday-evening admin session, line by line, and put a number on it. Spoiler: it’s measured in hours per week, not minutes.',
    description:
      'A worked example of an evening of trade admin — quote writing, chasing, invoicing — and how much of it AI can realistically take off your plate.',
    blocks: [
      {
        type: 'p',
        text: '“Saves you time” is the dullest claim in software marketing, because nobody ever says how much. So let’s do it properly. Below is a realistic Tuesday evening of admin for a sole-trader electrician, based on the pattern we hear from UK tradespeople again and again. We’ll go task by task, and be deliberately conservative.',
      },
      {
        type: 'p',
        text: 'The scene: three jobs completed today, one quote request from a new customer, one invoice still unpaid from last month, and a letting agent asking for an update.',
      },
      {
        type: 'h2',
        text: 'Task 1: the evening quote (60–90 min → ~20 min)',
      },
      {
        type: 'p',
        text: 'The old way: open a blank document, try to remember every part of “hallway rewire plus 6 downlights”, hunt through old quotes for the wording, look up parts on the merchant’s site, second-guess the price, format it so it looks professional. Easily an hour and a half.',
      },
      {
        type: 'p',
        text: 'With AI drafting from a real catalogue: you speak or type the job as you’d describe it to a mate, the draft appears with labour lines and materials already listed, and you spend twenty minutes checking, adjusting and sending. **Saving: around an hour, on a task that happens several times a week.**',
      },
      {
        type: 'h2',
        text: 'Task 2: chasing the quiet quote (15 min → 2 min)',
      },
      {
        type: 'p',
        text: 'Someone got your quote last week and went silent. The old way is to stare at the thread, write something that sounds friendly but not desperate, and feel mildly awkward about the whole thing. With a drafted chase message you can edit and send in two minutes, the awkwardness goes, and — this is the important bit — **the chase actually happens.** Unsent chases save no time at all; they just quietly cost you jobs.',
      },
      {
        type: 'h2',
        text: 'Task 3: invoicing today’s jobs (45 min → 10 min)',
      },
      {
        type: 'p',
        text: 'Three jobs, three invoices. The slow part is rarely the totals — it’s the descriptions, the formatting, making it look like a real business. When the invoice generates from the quote and job record you already have, you’re mostly reviewing and sending. **Saving: half an hour, three times a week is an hour and a half.**',
      },
      {
        type: 'h2',
        text: 'Task 4: the letting agent’s email thread (20 min → 5 min)',
      },
      {
        type: 'p',
        text: 'Buried in a fourteen-message thread is the actual brief: which property, which circuits, what certification they need, and by when. Reading the whole thread to reconstruct it takes twenty minutes and a strong cup of tea. A summary of the thread into “what they want, by when, for how much” takes a couple of minutes to read and check. **Saving: a quarter of an hour — and, more usefully, the right answer.**',
      },
      {
        type: 'h2',
        text: 'The honest total',
      },
      {
        type: 'ul',
        items: [
          'Quote drafting: roughly an hour saved, several times a week',
          'Chasing and customer messages: 15–30 minutes saved, most evenings',
          'Invoicing: 30–45 minutes saved on job days',
          'The mental overhead of starting: harder to measure, but real — editing a draft is far easier than facing a blank page',
        ],
      },
      {
        type: 'p',
        text: 'Add that up conservatively and you land at **four to six hours a week**. That’s most of a working evening, back — every single week. It’s not a magic wand: you still review everything, and the first few uses take longer while you calibrate. But the tradespeople we talk to consistently describe the same shift: admin stops being the thing that eats the evening, and becomes the thing that takes twenty minutes after tea.',
      },
      {
        type: 'quote',
        text: 'Nobody bills for the quote. The faster the paperwork moves, the more of the day is actually earning.',
      },
      {
        type: 'p',
        text: 'If you want to test the claim rather than take our word for it: time your next three evenings of admin as they are now, then try drafting your next three quotes with a tool like ours. We’re biased, obviously — but the stopwatch isn’t.',
      },
    ],
  },
  {
    slug: 'claim-back-admin-time',
    title: 'Claim your evenings back: a field guide to escaping admin as a tradesperson',
    date: '2026-09-10',
    readMinutes: 7,
    excerpt:
      'Process first, software second. The admin habits that quietly cost UK tradespeople their evenings — and the specific fixes, from templates to chasing.',
    description:
      'A practical field guide to reducing trade admin: same-day invoicing, templates, a fixed admin slot, chasing, and where software genuinely helps.',
    blocks: [
      {
        type: 'p',
        text: 'Ask a room of UK tradespeople what they’d change about running their business and the answer is almost always the same: less paperwork, fewer evenings at the kitchen table. The admin isn’t the job — but it’s the part that follows you home. Here’s how to shrink it, in the order that actually works.',
      },
      {
        type: 'h2',
        text: 'Fix the process before you buy software',
      },
      {
        type: 'p',
        text: 'Software poured onto a broken process just helps you do the wrong thing faster. A few process rules do most of the heavy lifting:',
      },
      {
        type: 'ul',
        items: [
          '**Invoice the moment the job is done, from the van.** Every day an invoice waits, its odds of being paid quickly drop — and it joins a backlog that only grows. Same-day invoicing is the single highest-value admin habit there is.',
          '**Quote within 24 hours or not at all.** Speed wins work. A decent quote sent tonight beats a perfect quote sent Friday. Letting it sit doesn’t make it better — it makes it stale.',
          '**One admin slot, not drip-fed admin.** Batch the paperwork into a fixed 30–45 minute window. Constant partial attention costs more than the task itself.',
          '**Chase on a schedule, not on a feeling.** Day 7 after the due date, polite message. Day 14, firmer. Day 21, call. Automate the reminder if you can; the point is that it happens every time.',
          '**Dictate on site.** Two minutes of voice notes in the van beats twenty minutes of “what did we actually do here?” at 9pm.',
        ],
      },
      {
        type: 'h2',
        text: 'Templates: boring, and worth their weight',
      },
      {
        type: 'p',
        text: 'Most trade admin is the same five documents wearing different hats. Build good templates once — quote, invoice, chase message, “job booked” confirmation, “running late” text — and never compose them from scratch again. If you find yourself typing a sentence for the third time, that sentence belongs in a template.',
      },
      {
        type: 'p',
        text: 'This is also where AI earns its keep in 2026: not replacing your templates, but generating the personalised first draft of each one so you’re always editing, never staring at a blank page.',
      },
      {
        type: 'h2',
        text: 'Where software actually fits',
      },
      {
        type: 'p',
        text: 'Once the process is sound, software removes the friction that remains. The things worth paying for, in rough order of value:',
      },
      {
        type: 'ul',
        items: [
          'Quotes and invoices that generate from the job record — no retyping',
          'A parts catalogue with current prices, so you stop checking the merchant site for every line',
          'Automatic, scheduled chase messages for quiet quotes and overdue invoices',
          'Everything in your pocket, not on a office PC you never turn on',
        ],
      },
      {
        type: 'p',
        text: 'Notice what’s *not* on that list: feature checklists with forty items you’ll never touch. The tools that win in a van are the ones that make the five daily jobs nearly frictionless. Complexity is the enemy — every extra screen is admin wearing a disguise.',
      },
      {
        type: 'h2',
        text: 'The two traps',
      },
      {
        type: 'p',
        text: '**Trap one: the admin perfectionism.** The quote doesn’t need to be literature. Professional, clear, fast — that’s the bar. **Trap two: the “I’ll do it Sunday” pile.** Admin debt compounds like financial debt. A small daily habit beats a heroic weekly session every time.',
      },
      {
        type: 'quote',
        text: 'The goal isn’t to love admin. It’s to make it small enough that it stops following you home.',
      },
      {
        type: 'p',
        text: 'None of this requires becoming a different person — just deciding that your evenings are worth defending, then giving the paperwork a smaller box to live in. It’s also the entire reason we built My Trade Portal: quotes, chasing and invoicing that take minutes, from the van, on your phone. In beta now, free while it is — worth a look if the kitchen-table paperwork has worn thin.',
      },
    ],
  },
  {
    slug: 'tradify-jobber-alternatives',
    title: 'Alternatives to Tradify and Jobber for UK electricians',
    date: '2026-09-11',
    readMinutes: 8,
    excerpt:
      'Tradify and Jobber dominate the search results, but they’re not the only options — and they’re not built for the UK. An honest look at the field, including us.',
    description:
      'An honest comparison of Tradify, Jobber, ServiceM8, Powered Now, simPRO and My Trade Portal for UK electricians — features, pricing models and UK fit.',
    blocks: [
      {
        type: 'p',
        text: 'Type “job management software for electricians” into Google and you’ll meet Tradify and Jobber almost immediately. Both are established, both are capable — and both leave a fair number of UK electricians feeling like they’ve bought a tool built for someone else’s market. If that’s you, here’s an honest survey of the alternatives, including the one we make. We’ll keep it factual and flag our own bias where it counts.',
      },
      {
        type: 'h2',
        text: 'First: what “UK fit” actually means',
      },
      {
        type: 'p',
        text: 'Plenty of software works anywhere in principle. UK fit is about the details that differ: VAT handling and HMRC-friendly invoicing, UK parts catalogues and merchant pricing, consumer-unit and certification vocabulary, and pricing in pounds without currency gymnastics. A tool can tick every feature box and still make you translate everything in your head.',
      },
      {
        type: 'h2',
        text: 'The established names',
      },
      {
        type: 'p',
        text: '**Tradify.** Job management with a strong track record in Australia and New Zealand and a real presence in the UK. Generally priced per user per month, with a free trial. Solid scheduling and job tracking; the quoting side is functional rather than fast, and it’s built for general trades rather than electrical specifics.',
      },
      {
        type: 'p',
        text: '**Jobber.** Polished, well-marketed, North American at its core. Per-user monthly pricing, tiered by feature set. Genuinely nice customer experience touches, but UK trades often report the catalogue, terminology and support hours feeling foreign — check the details against your workflow before committing.',
      },
      {
        type: 'p',
        text: '**ServiceM8.** Popular with Aussie tradies, pricing scales with the number of jobs you run per month rather than pure per-user fees, which can suit growing firms. Capable, though again UK parts data isn’t its home turf.',
      },
      {
        type: 'p',
        text: '**Powered Now.** UK-based, which shows in the invoicing and VAT handling. Aimed at small trade businesses broadly; feature depth varies by plan, also priced per user per month.',
      },
      {
        type: 'p',
        text: '**simPRO.** The enterprise end: quoting, projects, stock, gas and electrical certification modules. Serious capability and a serious price to match, with implementation to go with it. For a one-or-two-van operation it’s usually more tool than the job needs.',
      },
      {
        type: 'ul',
        items: [
          'All of the above are legitimate products with real customers — we’re not here to trash anyone',
          'Most are priced per user per month, tiered by features; free trials are common, so test before you commit',
          'The differences that matter are UK parts data, VAT-ready paperwork, and how fast a quote actually goes out',
        ],
      },
      {
        type: 'h2',
        text: 'Where My Trade Portal fits (honestly)',
      },
      {
        type: 'p',
        text: 'We built My Trade Portal for one trade first — UK electricians — and for the jobs that dominate a sole trader’s week: quoting, customer comms and invoicing, from an iPhone. The AI quote engine drafts guide-priced, ex-VAT line items from a plain-English job description, grounded in a UK parts catalogue, and every line is yours to edit before it goes out. Chasing and invoicing sit right there with it.',
      },
      {
        type: 'p',
        text: 'Now the honest caveats, because you deserve them: **we’re new, and we’re in beta.** That means free access while we finish baking, direct access to the people building it, and a product that improves weekly. It also means we’re iOS-only for now, we don’t yet do scheduling or job tracking like Tradify does, and you’d be an early adopter, not customer number fifty thousand. Some people love that; some need the safer established choice. Both are reasonable.',
      },
      {
        type: 'h2',
        text: 'How to choose',
      },
      {
        type: 'ul',
        items: [
          'List the three admin tasks that actually eat your week — buy for those, not for feature checklists',
          'Trial everything for a real week, on real jobs, before paying anything',
          'Check UK specifics on each trial: VAT invoices, parts data, support hours',
          'Count the taps to send a quote. That number is the product.',
        ],
      },
      {
        type: 'quote',
        text: 'The best software for a tradesperson is the one that’s still used in February.',
      },
      {
        type: 'p',
        text: 'If a fast, UK-first quoting flow sounds like your kind of thing, My Trade Portal is on TestFlight now and free during beta. And if you try it alongside the established names and the others win — genuinely, take the tool that fits. The only bad choice is another year of kitchen-table paperwork.',
      },
    ],
  },
]

export const getPostBySlug = (slug: string): BlogPost | undefined =>
  posts.find((p) => p.slug === slug)

export const formatDate = (iso: string): string =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
