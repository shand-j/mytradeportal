export interface Tier {
  name: string
  id: 'sole_trader' | 'pro' | 'team'
  tagline: string
  audience: string
  /** Plain-English AI allowance line shown on the card. */
  aiAllowance: string
  features: string[]
  featured: boolean
  /** Minimum seats (Team only). */
  minSeats?: number
  /** Static launch prices used when Paddle isn't configured or preview fails. */
  fallbackPrice: { month: string; year: string }
  /** Monthly/yearly Paddle price IDs — empty string when not configured. */
  priceId: { month: string; year: string }
}

/**
 * Confirmed launch pricing. Sole Trader overage is a hard block (upgrade
 * prompt); Pro and Team overage is metered at 6p per AI action with a monthly
 * spend cap and usage alerts.
 */
export const PricingTiers: Tier[] = [
  {
    name: 'Sole Trader',
    id: 'sole_trader',
    tagline: 'One-person bands getting quotes out faster.',
    audience: 'For self-employed tradespeople',
    aiAllowance:
      '30 AI quotes a month included — hit the limit and we\u2019ll nudge you to upgrade, never cut you off mid-job.',
    features: [
      'AI quote drafting',
      'Unlimited quotes & customers',
      'Invoicing & calendar',
      'Customer chat',
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
    aiAllowance:
      '100 AI quotes a month included, then 6p per extra quote, capped — we\u2019ll warn you first.',
    features: [
      'Everything in Sole Trader',
      'AI follow-up chat for customers',
      'Branded quotes & invoices',
      'Priority support',
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
    audience: 'For growing firms, 3 seats and up',
    aiAllowance:
      '100 AI quotes a month per seat, pooled across the team — then 6p per extra quote, capped — we\u2019ll warn you first.',
    features: [
      'Everything in Pro',
      'Multi-user access',
      'Advanced reporting',
      'Onboarding help',
    ],
    featured: false,
    minSeats: 3,
    fallbackPrice: { month: '£29', year: '£290' },
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
