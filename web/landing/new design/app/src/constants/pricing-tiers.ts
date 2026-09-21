export interface Tier {
  name: string
  id: 'sole_trader' | 'pro' | 'team'
  tagline: string
  audience: string
  /** Short differentiator line shown in the bordered box on the card. */
  highlight: string
  features: string[]
  featured: boolean
  /** Static launch prices used when Paddle isn't configured or preview fails. */
  fallbackPrice: { month: string; year: string }
  /** Monthly/yearly Paddle price IDs — empty string when not configured. */
  priceId: { month: string; year: string }
}

/**
 * Launch pricing: flat per business, unlimited users, AI unmetered on every
 * plan (subject to the fair-use policy at /fair-use). Provisional until the
 * beta evidence review.
 */
export const PricingTiers: Tier[] = [
  {
    name: 'Sole Trader',
    id: 'sole_trader',
    tagline: 'One-person bands getting quotes out faster.',
    audience: 'For self-employed tradespeople',
    highlight: 'Everything you need to quote, win the job, and get paid.',
    features: [
      'Customer portal',
      'AI quote drafting',
      'AI intake briefs',
      'Quote & payment chase sequences',
      'Online card payments',
      'Data export',
    ],
    featured: false,
    fallbackPrice: { month: '£25', year: '£250' },
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_SOLE_TRADER_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_SOLE_TRADER_YEAR ?? '',
    },
  },
  {
    name: 'Pro',
    id: 'pro',
    tagline: 'Busy sparks who want the whole pipeline.',
    audience: 'Most popular for working electricians',
    highlight: 'Adds the AI that does the looking — photos, drawings, and customer chat.',
    features: [
      'Everything in Sole Trader',
      'Photo & drawing analysis',
      'Customer-facing AI chat assistant',
      'Certificates',
      'Deposits & optional quote lines',
      'Offline mode',
      'Priority AI models',
    ],
    featured: true,
    fallbackPrice: { month: '£39', year: '£390' },
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_PRO_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_PRO_YEAR ?? '',
    },
  },
  {
    name: 'Team',
    id: 'team',
    tagline: 'Firms with multiple jobs on the go.',
    audience: 'For growing firms with people to coordinate',
    highlight: 'Runs the whole firm — every user included at no extra cost.',
    features: [
      'Everything in Pro',
      'Multi-user scheduling',
      'Roles & permissions',
      'Shared customer portal',
      'Team reporting',
    ],
    featured: false,
    fallbackPrice: { month: '£69', year: '£690' },
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_TEAM_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_TEAM_YEAR ?? '',
    },
  },
]

/** Tiers that have at least one Paddle price configured. */
export const configuredTiers = PricingTiers.filter(
  (t) => t.priceId.month || t.priceId.year,
)

export const hasYearlyPricing = configuredTiers.some((t) => t.priceId.year)
