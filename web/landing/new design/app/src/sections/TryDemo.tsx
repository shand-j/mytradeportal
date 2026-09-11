import { useEffect, useRef, useState } from 'react'
import {
  captureUtm,
  type DemoLineItem,
  DemoApiError,
  generateQuote,
  refineQuote,
  type DemoQuote,
} from '@/lib/demo-api'

const MIN_CHARS = 20
const MAX_CHARS = 4000

const gbp = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP' })

function SkeletonRows() {
  // Fixed pseudo-random widths so the layout is stable between renders.
  const widths = ['88%', '72%', '94%', '61%', '80%', '70%']
  return (
    <div aria-hidden className="space-y-[var(--space-sm)]">
      {widths.map((w, i) => (
        <div key={i} className="flex items-center gap-[var(--space-md)] py-1.5">
          <div className="demo-skeleton-bar h-3.5" style={{ width: w }} />
          <div className="demo-skeleton-bar ml-auto h-3.5 w-14 shrink-0" />
        </div>
      ))}
    </div>
  )
}

function QuoteSkeleton() {
  return (
    <div className="border-[1.5px] border-[var(--ink)] bg-[var(--paper)] p-[var(--space-lg)] shadow-[4px_4px_0_0_var(--ink)]">
      <div className="mb-[var(--space-md)] flex items-center justify-between border-b border-[var(--rule)] pb-[var(--space-sm)]">
        <div className="demo-skeleton-bar h-3.5 w-28" />
        <div className="demo-skeleton-bar h-3.5 w-16" />
      </div>
      <SkeletonRows />
      <div className="mt-[var(--space-md)] space-y-[var(--space-xs)] border-t border-[var(--rule)] pt-[var(--space-md)]">
        <div className="flex justify-end">
          <div className="demo-skeleton-bar h-3.5 w-40" />
        </div>
        <div className="flex justify-end">
          <div className="demo-skeleton-bar h-7 w-52" />
        </div>
      </div>
      <p className="spec-label mt-[var(--space-lg)] text-[var(--muted)]">Generating your quote…</p>
    </div>
  )
}

function confidenceTier(confidence: number): { label: string; className: string } {
  const pct = confidence <= 1 ? confidence * 100 : confidence
  if (pct >= 75) return { label: 'High confidence', className: 'border-[#1a7f37] text-[#1a7f37]' }
  if (pct >= 45) return { label: 'Medium confidence', className: 'border-[var(--accent-dark)] text-[var(--accent-dark)]' }
  return { label: 'Low confidence', className: 'border-[#b42318] text-[#b42318]' }
}

function QuoteCard({ quote }: { quote: DemoQuote }) {
  const tier = confidenceTier(quote.ai.confidence)
  return (
    <div className="border-[1.5px] border-[var(--ink)] bg-[var(--paper)] shadow-[4px_4px_0_0_var(--ink)]">
      <div className="flex flex-wrap items-center justify-between gap-[var(--space-sm)] border-b-2 border-[var(--ink)] px-[var(--space-lg)] py-[var(--space-sm)]">
        <span className="spec-label">Guide quote · ex-VAT line items</span>
        <span className={`spec-label border-[1.5px] px-2 py-0.5 ${tier.className}`}>
          {tier.label}
        </span>
      </div>

      <div className="overflow-x-auto px-[var(--space-lg)] py-[var(--space-md)]">
        <table className="w-full min-w-[520px] border-collapse text-[14px]">
          <thead>
            <tr className="spec-label border-b border-[var(--rule)] text-left text-[var(--muted)]">
              <th className="py-2 pr-4 font-medium">Description</th>
              <th className="w-16 py-2 pr-4 text-right font-medium">Qty</th>
              <th className="w-16 py-2 pr-4 text-left font-medium">Unit</th>
              <th className="w-24 py-2 pr-4 text-right font-medium">Unit price</th>
              <th className="w-24 py-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {quote.line_items.map((item, i) => (
              <LineRow key={`${i}-${item.description}`} item={item} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-[var(--space-2xs)] border-t-2 border-[var(--ink)] px-[var(--space-lg)] py-[var(--space-md)]">
        <div className="tnum flex justify-between text-[14px] text-[var(--muted)]">
          <span>Subtotal</span>
          <span>{gbp.format(quote.subtotal)}</span>
        </div>
        <div className="tnum flex justify-between text-[14px] text-[var(--muted)]">
          <span>VAT ({(quote.vat_rate * 100).toFixed(0)}%)</span>
          <span>{gbp.format(quote.vat_amount)}</span>
        </div>
        <div className="tnum flex justify-between pt-[var(--space-xs)] font-display text-[1.35rem] font-extrabold tracking-[-0.01em]">
          <span>Total</span>
          <span>{gbp.format(quote.total)}</span>
        </div>
      </div>

      {(quote.ai.assumptions.length > 0 || quote.ai.warnings.length > 0 || quote.ai.notes) && (
        <div className="space-y-[var(--space-xs)] border-t border-[var(--rule)] px-[var(--space-lg)] py-[var(--space-md)]">
          {quote.ai.assumptions.length > 0 && (
            <details>
              <summary className="spec-label cursor-pointer select-none text-[var(--ink)]">
                Assumptions ({quote.ai.assumptions.length})
              </summary>
              <ul className="mt-[var(--space-xs)] list-inside list-square space-y-[var(--space-2xs)] text-[13.5px] leading-[1.65] text-[var(--muted)]">
                {quote.ai.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </details>
          )}
          {quote.ai.warnings.length > 0 && (
            <details>
              <summary className="spec-label cursor-pointer select-none text-[var(--ink)]">
                Warnings ({quote.ai.warnings.length})
              </summary>
              <ul className="mt-[var(--space-xs)] list-inside list-square space-y-[var(--space-2xs)] text-[13.5px] leading-[1.65] text-[var(--muted)]">
                {quote.ai.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </details>
          )}
          {quote.ai.notes && (
            <p className="text-[13.5px] leading-[1.65] text-[var(--muted)]">{quote.ai.notes}</p>
          )}
        </div>
      )}

      <p className="spec-label border-t border-[var(--rule)] px-[var(--space-lg)] py-[var(--space-sm)] text-[var(--muted)]">
        Generated in {quote.generation_seconds.toFixed(1)}s · {quote.retrieval_status}
      </p>
    </div>
  )
}

function LineRow({ item }: { item: DemoLineItem }) {
  return (
    <tr className="border-b border-[var(--rule)] last:border-0">
      <td className="py-2.5 pr-4 align-top">
        {item.description}
        {item.ai_generated && (
          <span className="spec-label ml-2 border border-[var(--rule)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
            AI
          </span>
        )}
      </td>
      <td className="tnum py-2.5 pr-4 text-right align-top">{item.quantity}</td>
      <td className="py-2.5 pr-4 align-top text-[var(--muted)]">{item.unit}</td>
      <td className="tnum py-2.5 pr-4 text-right align-top">{gbp.format(item.unit_price)}</td>
      <td className="tnum py-2.5 text-right align-top font-semibold">{gbp.format(item.total)}</td>
    </tr>
  )
}

/**
 * TryDemo — public, login-free demo of the AI quote pipeline. Everything is
 * ephemeral: nothing is stored in localStorage, cookies, or sent anywhere
 * except the demo endpoints (with UTM params forwarded for attribution).
 */
export default function TryDemo() {
  const [description, setDescription] = useState('')
  const [quote, setQuote] = useState<DemoQuote | null>(null)
  const [quoteDescription, setQuoteDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [busy, setBusy] = useState<'generate' | 'refine' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const canGenerate = description.trim().length >= MIN_CHARS && busy === null
  const canRefine = instructions.trim().length >= 3 && busy === null && quote !== null

  /* Abort any in-flight request when the section unmounts. */
  useEffect(() => {
    const ref = abortRef
    return () => ref.current?.abort()
  }, [])

  const run = async (kind: 'generate' | 'refine') => {
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(kind)
    setError(null)
    try {
      const next =
        kind === 'generate'
          ? await generateQuote(
              { description: description.trim(), ...captureUtm() },
              controller.signal,
            )
          : await refineQuote(
              {
                description: quoteDescription,
                instructions: instructions.trim(),
                line_items: quote?.line_items ?? [],
              },
              controller.signal,
            )
      if (kind === 'generate') setQuoteDescription(description.trim())
      setQuote(next)
      setInstructions('')
    } catch (err) {
      if (err instanceof DemoApiError) {
        setError(err.message)
      } else if (err instanceof Error && err.name === 'AbortError') {
        // unmounted or superseded — leave state untouched
      } else {
        setError('Network hiccup — please try again.')
      }
    } finally {
      setBusy(null)
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  return (
    <section id="try-ai" className="border-b-2 border-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <div className="mb-[var(--space-3xl)] max-w-[52ch]">
          <h2 className="reveal font-display text-[clamp(2rem,4.4vw,4rem)] leading-[0.98] font-extrabold tracking-[-0.02em] text-[var(--ink)]">
            Try the AI. Right here.
          </h2>
          <p className="reveal mt-[var(--space-md)] text-[15.5px] leading-[1.75] text-[var(--muted)]" style={{ ['--i' as string]: 1 }}>
            Type an electrical job below and watch a guide-priced quote get
            drafted — the same engine the app runs on. No login, no email,
            nothing saved.
          </p>
        </div>

        <div className="grid gap-[var(--space-lg)] lg:grid-cols-12">
          {/* Input column */}
          <div className="reveal lg:col-span-5" style={{ ['--i' as string]: 2 }}>
            <div className="border-[1.5px] border-[var(--ink)] bg-[var(--paper)] p-[var(--space-lg)] shadow-[4px_4px_0_0_var(--ink)]">
              <label htmlFor="demo-description" className="spec-label text-[var(--ink)]">
                Describe the job
              </label>
              <textarea
                id="demo-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={MAX_CHARS}
                rows={6}
                placeholder="e.g. Install 6 LED downlights in a kitchen ceiling, add a double socket in the utility room…"
                className="mt-[var(--space-sm)] w-full resize-y border-[1.5px] border-[var(--ink)] bg-[var(--paper)] px-3 py-2.5 text-[15px] leading-[1.6] placeholder:text-[var(--muted)]/70"
              />
              <div className="mt-[var(--space-xs)] flex items-center justify-between">
                <span className="font-mono text-[11px] text-[var(--muted)]">
                  {description.length}/{MAX_CHARS}
                  {description.length > 0 && description.trim().length < MIN_CHARS && (
                    <span className="text-[var(--accent-dark)]">
                      {' '}
                      · min {MIN_CHARS} chars
                    </span>
                  )}
                </span>
              </div>
              <button
                type="button"
                disabled={!canGenerate}
                onClick={() => void run('generate')}
                className="chip chip--fill mt-[var(--space-md)] w-full justify-center disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === 'generate' ? 'Generating…' : 'Generate quote'}
              </button>
              <p className="mt-[var(--space-sm)] text-[12.5px] leading-[1.6] text-[var(--muted)]">
                Guide prices only — ex-VAT trade rates for typical UK domestic
                work. The full app lets you edit every line before it goes out.
              </p>
            </div>
          </div>

          {/* Result column */}
          <div className="reveal lg:col-span-7" style={{ ['--i' as string]: 3 }}>
            {error && (
              <div role="alert" className="mb-[var(--space-md)] border-[1.5px] border-[var(--accent-dark)] bg-[var(--accent)]/15 px-4 py-3 text-[14px] font-medium text-[var(--ink)]">
                {error}
              </div>
            )}

            <div aria-live="polite">
              {busy !== null ? (
                <QuoteSkeleton />
              ) : quote ? (
                <QuoteCard quote={quote} />
              ) : (
                <div className="flex min-h-[280px] items-center justify-center border-[1.5px] border-dashed border-[var(--rule)] p-[var(--space-lg)]">
                  <p className="spec-label max-w-[32ch] text-center leading-[1.8] text-[var(--muted)]">
                    Your draft quote will appear here — line items, VAT and all
                  </p>
                </div>
              )}
            </div>

            {quote && busy === null && (
              <div className="mt-[var(--space-md)] border-[1.5px] border-[var(--ink)] bg-[var(--paper)] p-[var(--space-lg)]">
                <label htmlFor="demo-instructions" className="spec-label text-[var(--ink)]">
                  Refine with AI
                </label>
                <div className="mt-[var(--space-sm)] flex flex-col gap-[var(--space-sm)] sm:flex-row">
                  <input
                    id="demo-instructions"
                    type="text"
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    maxLength={1000}
                    placeholder='e.g. "make it cheaper" or "assume the consumer unit needs upgrading"'
                    className="min-w-0 flex-1 border-[1.5px] border-[var(--ink)] bg-[var(--paper)] px-3 py-2.5 text-[14.5px] placeholder:text-[var(--muted)]/70"
                  />
                  <button
                    type="button"
                    disabled={!canRefine}
                    onClick={() => void run('refine')}
                    className="chip justify-center disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busy === 'refine' ? 'Refining…' : 'Refine with AI'}
                  </button>
                </div>
                <p className="mt-[var(--space-xs)] text-[12.5px] text-[var(--muted)]">
                  The whole quote is regenerated with your instruction — line
                  items come back re-priced.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
