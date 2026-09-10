"use client";

import {
  type Environments,
  initializePaddle,
  type Paddle,
} from "@paddle/paddle-js";
import { useEffect, useState } from "react";
import { usePaddlePrices } from "@/hooks/usePaddlePrices";
import {
  configuredTiers,
  hasYearlyPricing,
  PricingTier,
} from "@/constants/pricing-tier";
import { TESTFLIGHT_URL } from "@/lib/site";

/**
 * Pricing — prices are pulled live from Paddle (PricePreview), localised to
 * the visitor's country with tax handled by Paddle. During beta every plan
 * is free; shown prices are the launch prices.
 */
export function Pricing({ country }: { country: string }) {
  const tiers = configuredTiers.length > 0 ? configuredTiers : PricingTier;
  const showToggle = hasYearlyPricing;
  const [frequency, setFrequency] = useState<"month" | "year">("month");
  const [paddle, setPaddle] = useState<Paddle | undefined>();
  const paddleConfigured = Boolean(process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN);

  const { prices, loading } = usePaddlePrices(
    paddleConfigured ? paddle : undefined,
    country,
  );

  useEffect(() => {
    if (!paddleConfigured) return;
    initializePaddle({
      token: process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN as string,
      environment: process.env.NEXT_PUBLIC_PADDLE_ENV as Environments,
    }).then((p) => p && setPaddle(p));
  }, [paddleConfigured]);

  return (
    <section className="section" id="pricing">
      <div className="wrap">
        <div className="section-head">
          <h2>Pricing</h2>
          <p>
            Free while we&apos;re in beta — join TestFlight and every plan is
            unlocked. These are the launch prices, localised to your currency.
          </p>
        </div>

        {showToggle && (
          <div className="freq-toggle" role="group" aria-label="Billing frequency">
            <button
              type="button"
              className={frequency === "month" ? "is-active" : ""}
              onClick={() => setFrequency("month")}
            >
              Monthly
            </button>
            <button
              type="button"
              className={frequency === "year" ? "is-active" : ""}
              onClick={() => setFrequency("year")}
            >
              Yearly
            </button>
          </div>
        )}

        <div className="tiers">
          {tiers.map((tier) => {
            const priceId = tier.priceId[frequency] || tier.priceId.month;
            const formatted = priceId ? prices[priceId] : undefined;
            return (
              <article
                key={tier.id}
                className={`tier ${tier.featured ? "tier-featured" : ""}`}
              >
                <p className="tier-audience">{tier.audience}</p>
                <h3>{tier.name}</h3>
                <p className="tier-desc">{tier.description}</p>
                <p className="tier-price" aria-live="polite">
                  {loading && formatted === undefined && paddleConfigured ? (
                    <span className="tier-price-loading">···</span>
                  ) : formatted ? (
                    <>
                      <span className="tier-amount">{formatted}</span>
                      <span className="tier-per">
                        /{frequency === "year" ? "yr" : "mo"}
                      </span>
                    </>
                  ) : (
                    <span className="tier-price-unconfigured">Beta — free</span>
                  )}
                </p>
                <ul className="tier-features">
                  {tier.features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <a
                  className={`btn ${tier.featured ? "btn-primary" : "btn-outline"} tier-cta`}
                  href={TESTFLIGHT_URL}
                >
                  Join the beta
                </a>
              </article>
            );
          })}
        </div>

        <p className="pricing-note">
          Prices shown with local tax where applicable, via Paddle. Plan
          features are being finalised during beta — what you see now is what
          we intend to ship.
        </p>
      </div>
    </section>
  );
}
