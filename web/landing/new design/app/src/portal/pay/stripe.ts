import { loadStripe, type Stripe } from '@stripe/stripe-js'

export const PUBLISHABLE_KEY = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY as string | undefined

let stripePromise: Promise<Stripe | null> | null = null

export function getStripe(key: string): Promise<Stripe | null> {
  if (!stripePromise) stripePromise = loadStripe(key)
  return stripePromise
}

export function buildElementsOptions(clientSecret: string, brandColor: string) {
  return {
    clientSecret,
    appearance: {
      theme: 'stripe' as const,
      variables: {
        colorPrimary: brandColor,
        borderRadius: '2px',
      },
    },
  }
}
