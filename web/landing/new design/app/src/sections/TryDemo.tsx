import { useEffect, useRef, useState } from 'react'
import PhoneFrame from '../components/PhoneFrame'
import { TESTFLIGHT_URL } from '@/lib/site'
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

/* ------------------------------------------------------------------ */
/* App-style primitives — mirror the real iOS app's visual language    */
/* (white cards, rounded-2xl, slate borders, blue primary, soft pills) */
/* ------------------------------------------------------------------ */

function ChevronLeft() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 18l-6-6 6-6"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function Sparkles({ className = 'text-[#2563eb]' }: { className?: string }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 2l2.1 6.4L21 10.5l-6.9 2.1L12 19l-2.1-6.4L3 10.5l6.9-2.1L12 2z" />
    </svg>
  )
}

/** App header: back chevron + centered bold title, clearing the dynamic island. */
function AppHeader({ title, onBack }: { title: string; onBack?: () => void }) {
  return (
    <div className="relative flex items-center justify-center px-3 pb-2.5 pt-11">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          aria-label="Back"
          className="absolute left-2 top-11 flex items-center gap-0.5 text-[13px] font-medium text-slate-900"
        >
          <ChevronLeft />
          Back
        </button>
      )}
      <p className="text-[15px] font-semibold text-slate-900">{title}</p>
    </div>
  )
}

function PulseBar({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200 ${className}`} />
}

/** Grey placeholder line-item cards, like the app's generating skeleton. */
function LineItemSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="space-y-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
          <div className="flex items-center justify-between">
            <PulseBar className="h-2.5 w-12" />
            <PulseBar className="h-2.5 w-8" />
          </div>
          <PulseBar className="h-3 w-full" />
          <div className="flex items-center justify-between pt-0.5">
            <PulseBar className="h-2.5 w-16" />
            <PulseBar className="h-3.5 w-14" />
          </div>
        </div>
      ))}
    </div>
  )
}

function confidencePct(confidence: number): number {
  return Math.round(confidence <= 1 ? confidence * 100 : confidence)
}

/* ------------------------------------------------------------------ */
/* Screen states                                                       */
/* ------------------------------------------------------------------ */

function IntakeScreen({
  description,
  setDescription,
  error,
  errorStatus,
  busy,
  onGenerate,
}: {
  description: string
  setDescription: (v: string) => void
  error: string | null
  errorStatus: number | null
  busy: boolean
  onGenerate: () => void
}) {
  const canGenerate = description.trim().length >= MIN_CHARS && !busy
  return (
    <div className="space-y-3 px-3 pb-4">
      <div className="space-y-2 rounded-2xl bg-slate-100 p-4">
        <label htmlFor="demo-description" className="block text-[13.5px] font-semibold text-slate-900">
          Job description
        </label>
        <textarea
          id="demo-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={MAX_CHARS}
          rows={7}
          placeholder="Describe the job in plain English, e.g. Replace consumer unit in a 3-bed semi…"
          className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-[13px] leading-relaxed text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#2563eb]/40"
        />
        <p className="text-right text-[10.5px] text-slate-400">
          {description.length}/{MAX_CHARS}
          {description.length > 0 && description.trim().length < MIN_CHARS && (
            <span className="text-amber-700"> · min {MIN_CHARS} chars</span>
          )}
        </p>
      </div>

      <div className="rounded-2xl bg-blue-50 p-4">
        <p className="text-[11.5px] leading-snug text-slate-600">
          The AI drafts guide-priced, ex-VAT line items from your description. In the
          full app you can edit every line before it goes out.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-2xl bg-amber-50 p-4">
          <p className="text-[11.5px] leading-snug text-amber-800">{error}</p>
          {errorStatus === 429 && (
            <a
              href={TESTFLIGHT_URL}
              className="mt-2 inline-flex items-center justify-center rounded-xl bg-[#2563eb] px-3.5 py-2 text-[12.5px] font-semibold text-white shadow-sm"
            >
              Join the beta
            </a>
          )}
        </div>
      )}

      <button
        type="button"
        disabled={!canGenerate}
        onClick={onGenerate}
        className="w-full rounded-xl bg-[#2563eb] py-3 text-[14.5px] font-semibold text-white shadow-sm transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? 'Generating…' : 'Generate quote'}
      </button>
      <p className="text-center text-[10.5px] leading-snug text-slate-500">
        Guide prices only — no login, nothing saved.
      </p>
    </div>
  )
}

function GeneratingScreen({ label = 'Generating quote…' }: { label?: string }) {
  return (
    <div className="space-y-3 px-3 pb-4">
      <div className="flex items-start gap-2.5 rounded-2xl border border-blue-100 bg-blue-50 p-3.5">
        <Sparkles />
        <div>
          <p className="text-[12.5px] font-semibold text-slate-900">Quote is generating</p>
          <p className="text-[11.5px] leading-snug text-slate-600">
            Drafting line items and guide prices…
          </p>
        </div>
      </div>

      <div className="flex flex-col items-center gap-2 pt-4">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-slate-200 border-t-[#2563eb]" />
        <p className="text-[13.5px] font-semibold text-slate-900">{label}</p>
        <p className="text-[11px] text-slate-500">Typical UK domestic trade rates</p>
        <p className="max-w-[240px] text-center text-[10.5px] leading-snug text-slate-400">
          This can take a minute or two — the AI is pricing real parts.
        </p>
      </div>

      <div className="pt-2">
        <LineItemSkeleton rows={3} />
      </div>
    </div>
  )
}

function ReviewScreen({
  quote,
  quoteDescription,
  instructions,
  setInstructions,
  error,
  refining,
  onRefine,
}: {
  quote: DemoQuote
  quoteDescription: string
  instructions: string
  setInstructions: (v: string) => void
  error: string | null
  refining: boolean
  onRefine: () => void
}) {
  const canRefine = instructions.trim().length >= 3 && !refining
  return (
    <div className="space-y-3 px-3 pb-4">
      {/* Job description + confidence pill */}
      <div className="space-y-1.5 rounded-xl bg-slate-100 p-3">
        <p className="text-[12.5px] font-semibold leading-snug text-slate-900">{quoteDescription}</p>
        <p className="text-[11px] text-slate-500">AI draft · guide prices · ex-VAT lines</p>
        <span className="inline-block rounded-md bg-blue-100 px-2 py-1 text-[10.5px] font-medium text-blue-800">
          AI confidence {confidencePct(quote.ai.confidence)}%
        </span>
      </div>

      {/* Assumptions / warnings — amber card, app-style bullets */}
      {(quote.ai.assumptions.length > 0 || quote.ai.warnings.length > 0) && (
        <div className="space-y-1.5 rounded-xl bg-amber-50 p-3">
          {quote.ai.warnings.map((w, i) => (
            <p key={`w-${i}`} className="text-[11px] leading-snug text-amber-800">
              • {w}
            </p>
          ))}
          {quote.ai.assumptions.map((a, i) => (
            <p key={`a-${i}`} className="text-[11px] leading-snug text-slate-600">
              • Assumed: {a}
            </p>
          ))}
        </div>
      )}
      {quote.ai.notes && (
        <p className="text-[11px] leading-snug text-slate-500">{quote.ai.notes}</p>
      )}

      {/* Line items */}
      {refining ? (
        <LineItemSkeleton rows={2} />
      ) : (
        quote.line_items.map((item, i) => <LineItemCard key={`${i}-${item.description}`} item={item} index={i} />)
      )}

      {/* Totals — Subtotal / VAT / Total, like the app's footer */}
      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        {refining ? (
          <div className="flex items-center justify-between" aria-hidden>
            <PulseBar className="h-6 w-24" />
            <PulseBar className="h-7 w-20" />
          </div>
        ) : (
          <div className="flex items-end justify-between">
            <div>
              <p className="text-[10.5px] text-slate-500">Subtotal</p>
              <p className="tnum text-[12px] font-medium text-slate-700">{gbp.format(quote.subtotal)}</p>
            </div>
            <div>
              <p className="text-[10.5px] text-slate-500">VAT ({(quote.vat_rate * 100).toFixed(0)}%)</p>
              <p className="tnum text-[12px] font-medium text-slate-700">{gbp.format(quote.vat_amount)}</p>
            </div>
            <div className="text-right">
              <p className="text-[10.5px] text-slate-500">Total</p>
              <p className="tnum text-[16px] font-bold text-slate-900">{gbp.format(quote.total)}</p>
            </div>
          </div>
        )}
      </div>

      {/* Refine with AI */}
      <div className="space-y-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <p className="flex items-center gap-1.5 text-[12.5px] font-semibold text-slate-900">
          <Sparkles className="text-[#d97706]" />
          Refine with AI
        </p>
        <input
          type="text"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          maxLength={1000}
          placeholder='e.g. "make it cheaper" or "assume the CU needs upgrading"'
          className="h-9 w-full rounded-lg border border-slate-200 px-3 text-[12px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#2563eb]/40"
        />
        {error && (
          <div role="alert" className="rounded-xl bg-amber-50 p-2.5">
            <p className="text-[11px] leading-snug text-amber-800">{error}</p>
          </div>
        )}
        <button
          type="button"
          disabled={!canRefine}
          onClick={onRefine}
          className="w-full rounded-xl bg-[#2563eb] py-2.5 text-[13px] font-semibold text-white shadow-sm transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {refining ? 'Refining…' : 'Refine quote'}
        </button>
      </div>

      <p className="text-center text-[10px] text-slate-400">
        Generated in {quote.generation_seconds.toFixed(1)}s · {quote.retrieval_status}
      </p>
    </div>
  )
}

function LineItemCard({ item, index }: { item: DemoLineItem; index: number }) {
  return (
    <div className="space-y-1.5 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] text-slate-400">Line {index + 1}</span>
        {item.ai_generated && (
          <span className="flex items-center gap-1 text-[10px] font-medium text-amber-700">
            <Sparkles className="text-[#d97706]" />
            AI
          </span>
        )}
      </div>
      <p className="text-[12.5px] leading-snug text-slate-900">{item.description}</p>
      <div className="flex items-end justify-between pt-0.5">
        <span className="tnum text-[11.5px] text-slate-500">
          {item.quantity} × {gbp.format(item.unit_price)}
        </span>
        <span className="tnum text-[13px] font-semibold text-slate-900">{gbp.format(item.total)}</span>
      </div>
    </div>
  )
}

/**
 * TryDemo — public, login-free demo of the AI quote pipeline, presented
 * inside the realistic phone frame so it reads as the app itself. Screen
 * content mirrors the real app's quote-intake and review-quote screens.
 * Everything is ephemeral: nothing is stored, and only the demo endpoints
 * are called (with UTM params forwarded for attribution).
 */
export default function TryDemo() {
  const [description, setDescription] = useState('')
  const [quote, setQuote] = useState<DemoQuote | null>(null)
  const [quoteDescription, setQuoteDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [busy, setBusy] = useState<'generate' | 'refine' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [errorStatus, setErrorStatus] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)

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
    setErrorStatus(null)
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
        setErrorStatus(err.status)
      } else if (err instanceof Error && err.name === 'AbortError') {
        // unmounted or superseded — leave state untouched
      } else {
        setError('Network hiccup — please try again.')
        setErrorStatus(null)
      }
    } finally {
      setBusy(null)
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  const reviewing = quote !== null
  const title = reviewing ? 'Review quote' : 'New quote'

  return (
    <PhoneFrame>
      <div className="flex h-full flex-col bg-[var(--cream)]">
        <AppHeader
          title={title}
          onBack={
            reviewing && busy === null
              ? () => {
                  setQuote(null)
                  setError(null)
                  setErrorStatus(null)
                  setInstructions('')
                }
              : undefined
          }
        />
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-live="polite">
          {busy === 'generate' ? (
            <GeneratingScreen />
          ) : reviewing ? (
            <ReviewScreen
              quote={quote}
              quoteDescription={quoteDescription}
              instructions={instructions}
              setInstructions={setInstructions}
              error={error}
              refining={busy === 'refine'}
              onRefine={() => void run('refine')}
            />
          ) : (
            <IntakeScreen
              description={description}
              setDescription={setDescription}
              error={error}
              errorStatus={errorStatus}
              busy={busy !== null}
              onGenerate={() => void run('generate')}
            />
          )}
        </div>
      </div>
    </PhoneFrame>
  )
}
