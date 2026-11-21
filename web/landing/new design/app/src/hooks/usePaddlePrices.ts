import {
  type Paddle,
  type PricePreviewParams,
  type PricePreviewResponse,
} from '@paddle/paddle-js'
import { useEffect, useState } from 'react'
import { configuredTiers } from '@/constants/pricing-tiers'

export type PaddlePrices = Record<string, string>

function getLineItems(): PricePreviewParams['items'] {
  return configuredTiers.flatMap((tier) =>
    [tier.priceId.month, tier.priceId.year]
      .filter(Boolean)
      .map((priceId) => ({ priceId, quantity: 1 })),
  )
}

function getPriceAmounts(prices: PricePreviewResponse): PaddlePrices {
  return prices.data.details.lineItems.reduce<PaddlePrices>((acc, item) => {
    acc[item.price.id] = item.formattedTotals.total
    return acc
  }, {})
}

const lineItems = getLineItems()

/**
 * Fetches formatted price amounts (per price ID) from Paddle PricePreview,
 * localised to the visitor's country. Tolerates unconfigured price IDs and
 * fetch failure — `prices` simply stays empty and `loading` becomes false.
 */
export function usePaddlePrices(
  paddle: Paddle | undefined,
  country: string,
): { prices: PaddlePrices; loading: boolean } {
  const requestKey = `${country}:${paddle ? 'ready' : 'waiting'}`
  const [result, setResult] = useState<{ requestKey: string | null; prices: PaddlePrices }>({
    requestKey: null,
    prices: {},
  })

  useEffect(() => {
    if (!paddle || lineItems.length === 0) return
    let cancelled = false

    const params: Partial<PricePreviewParams> = {
      items: lineItems,
      // 'OTHERS' is a sentinel meaning "let Paddle infer from IP".
      ...(country !== 'OTHERS' && { address: { countryCode: country } }),
    }

    paddle
      .PricePreview(params as PricePreviewParams)
      .then((response) => {
        if (cancelled) return
        setResult((prev) => ({
          requestKey,
          prices: { ...prev.prices, ...getPriceAmounts(response) },
        }))
      })
      .catch(() => {
        if (cancelled) return
        setResult((prev) => ({ ...prev, requestKey }))
      })
    return () => {
      cancelled = true
    }
  }, [country, paddle, requestKey])

  return {
    prices: result.prices,
    loading: lineItems.length > 0 && result.requestKey !== requestKey,
  }
}
