export interface Tier {
  name: string
  id: 'starter' | 'pro' | 'business'
  description: string
  audience: string
  features: string[]
  featured: boolean
  /** Monthly/yearly Paddle price IDs — empty string when not configured. */
  priceId: { month: string; year: string }
}

export const PricingTier: Tier[] = [
  {
    name: 'Starter',
    id: 'starter',
    description: 'Sole traders getting quotes out faster.',
    audience: 'For one-person bands',
    features: [
      'AI quote drafting',
      'Unlimited quotes & customers',
      'Invoicing & calendar',
      'Customer chat',
    ],
    featured: false,
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_STARTER_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_STARTER_YEAR ?? '',
    },
  },
  {
    name: 'Pro',
    id: 'pro',
    description: 'Busy sparks who want the whole pipeline.',
    audience: 'Most popular for working electricians',
    features: [
      'Everything in Starter',
      'AI follow-up chat for customers',
      'Branded quotes & invoices',
      'Priority support',
    ],
    featured: true,
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_PRO_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_PRO_YEAR ?? '',
    },
  },
  {
    name: 'Business',
    id: 'business',
    description: 'For firms with multiple jobs on the go.',
    audience: 'For growing firms',
    features: [
      'Everything in Pro',
      'Multi-user access',
      'Advanced reporting',
      'Onboarding help',
    ],
    featured: false,
    priceId: {
      month: import.meta.env.VITE_PADDLE_PRICE_BUSINESS_MONTH ?? '',
      year: import.meta.env.VITE_PADDLE_PRICE_BUSINESS_YEAR ?? '',
    },
  },
]

/** Tiers that have at least one Paddle price configured. */
export const configuredTiers = PricingTier.filter(
  (t) => t.priceId.month || t.priceId.year,
)

export const hasYearlyPricing = configuredTiers.some((t) => t.priceId.year)
