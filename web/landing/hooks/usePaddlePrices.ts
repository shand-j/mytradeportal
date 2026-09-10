"use client";

import {
  type Paddle,
  type PricePreviewParams,
  type PricePreviewResponse,
} from "@paddle/paddle-js";
import { useEffect, useState } from "react";
import { configuredTiers } from "@/constants/pricing-tier";

export type PaddlePrices = Record<string, string>;

function getLineItems(): PricePreviewParams["items"] {
  return configuredTiers.flatMap((tier) =>
    [tier.priceId.month, tier.priceId.year]
      .filter(Boolean)
      .map((priceId) => ({ priceId, quantity: 1 })),
  );
}

function getPriceAmounts(prices: PricePreviewResponse): PaddlePrices {
  return prices.data.details.lineItems.reduce<PaddlePrices>((acc, item) => {
    acc[item.price.id] = item.formattedTotals.total;
    return acc;
  }, {});
}

export function usePaddlePrices(
  paddle: Paddle | undefined,
  country: string,
): { prices: PaddlePrices; loading: boolean } {
  const [prices, setPrices] = useState<PaddlePrices>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!paddle) return;
    const items = getLineItems();
    if (items.length === 0) {
      setLoading(false);
      return;
    }

    const params: Partial<PricePreviewParams> = {
      items,
      // "OTHERS" is a sentinel meaning "let Paddle infer from IP".
      ...(country !== "OTHERS" && { address: { countryCode: country } }),
    };

    setLoading(true);
    paddle
      .PricePreview(params as PricePreviewParams)
      .then((response) => {
        setPrices((prev) => ({ ...prev, ...getPriceAmounts(response) }));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [country, paddle]);

  return { prices, loading };
}
