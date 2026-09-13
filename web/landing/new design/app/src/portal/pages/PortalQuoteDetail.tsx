import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { RequireAuth } from '../components/auth'
import { ChatThread, type ChatMessage } from '../components/ChatThread'
import { usePageMeta } from '../../hooks/usePageMeta'
import {
  acceptQuote,
  listCommunications,
  listQuotes,
  postCommunication,
  rejectQuote,
  SessionExpiredError,
  type CustomerQuote,
} from '../api'
import { DocumentLoading, formatDate, formatMoney, StatusBadge } from '../../pages/ViewQuote'

function StatusTimeline({ quote }: { quote: CustomerQuote }) {
  const steps: { label: string; at: string | null; done: boolean }[] = [
    { label: 'Created', at: quote.created_at, done: true },
    { label: 'Sent to you', at: quote.sent_at, done: quote.sent_at != null },
    {
      label: quote.status === 'rejected' ? 'Declined' : 'Accepted',
      at: quote.approved_at,
      done: quote.status === 'approved' || quote.status === 'rejected' || quote.status === 'invoiced',
    },
  ]
  return (
    <ol className="mt-[var(--space-lg)] space-y-0 border-l-2 border-[var(--rule)] pl-4">
      {steps.map((step) => (
        <li key={step.label} className="relative pb-4 last:pb-0">
          <span
            className="absolute -left-[23px] top-1 h-3 w-3 rounded-full border-2 border-[var(--ink)]"
            style={{ backgroundColor: step.done ? 'var(--accent)' : 'var(--paper)' }}
          />
          <p className={`text-[13.5px] font-semibold ${step.done ? '' : 'text-[var(--muted)]'}`}>
            {step.label}
          </p>
          {step.at && step.done && (
            <p className="text-[12px] text-[var(--muted)]">{formatDate(step.at)}</p>
          )}
        </li>
      ))}
    </ol>
  )
}

function AcceptPanel({
  quote,
  onDone,
  onCancel,
}: {
  quote: CustomerQuote
  onDone: (updated: CustomerQuote) => void
  onCancel: () => void
}) {
  const { slug } = usePortal()
  const [dates, setDates] = useState<string[]>([])
  const [newDate, setNewDate] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleConfirm() {
    if (submitting) return
    setSubmitting(true)
    setError('')
    try {
      const updated = await acceptQuote(
        slug,
        quote.id,
        dates.length > 0 ? dates.map((date) => ({ date })) : undefined,
      )
      onDone(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
      setSubmitting(false)
    }
  }

  return (
    <div className="mt-[var(--space-md)] border-2 border-[var(--ink)] bg-[var(--paper-2)] p-5">
      <p className="text-[14px] font-semibold">Accept this quote</p>
      <p className="mt-1 text-[13px] leading-relaxed text-[var(--muted)]">
        Optionally suggest the dates that suit you — your electrician will confirm the visit.
      </p>
      <div className="mt-[var(--space-sm)] flex flex-wrap items-center gap-2">
        {dates.map((date) => (
          <span
            key={date}
            className="inline-flex items-center gap-2 border-2 border-[var(--ink)] bg-[var(--paper)] px-2.5 py-1 text-[13px]"
          >
            {new Date(`${date}T00:00:00`).toLocaleDateString('en-GB', {
              day: 'numeric',
              month: 'short',
            })}
            <button
              type="button"
              aria-label={`Remove ${date}`}
              onClick={() => setDates((prev) => prev.filter((d) => d !== date))}
              className="font-bold"
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="date"
          value={newDate}
          min={new Date().toISOString().slice(0, 10)}
          onChange={(e) => setNewDate(e.target.value)}
          aria-label="Pick a preferred date"
          className="border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-1.5 text-[13.5px] focus:outline-none"
        />
        <button
          type="button"
          disabled={!newDate || dates.includes(newDate)}
          onClick={() => {
            setDates((prev) => [...prev, newDate])
            setNewDate('')
          }}
          className="border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-1.5 text-[12.5px] font-bold uppercase tracking-[0.06em] disabled:opacity-40"
        >
          Add
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-[var(--space-sm)] text-[13px] text-[var(--accent-dark)]">
          {error}
        </p>
      )}
      <div className="mt-[var(--space-md)] flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={submitting}
          className="chip chip--fill justify-center disabled:opacity-50"
        >
          {submitting ? 'Accepting…' : 'Confirm acceptance'}
        </button>
        <button type="button" onClick={onCancel} className="chip justify-center">
          Cancel
        </button>
      </div>
    </div>
  )
}

function DiscussPanel({ quote }: { quote: CustomerQuote }) {
  const { slug } = usePortal()
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [loadError, setLoadError] = useState('')

  const load = useCallback(() => {
    if (!quote.quote_request_id) return
    listCommunications(slug, quote.quote_request_id)
      .then((comms) => {
        setMessages(
          comms
            .filter((c) => c.body)
            .map((c) => ({
              id: c.id,
              role:
                c.sender_role === 'customer' ? 'customer' : c.sender_role === 'ai' ? 'ai' : 'business',
              body: c.body ?? '',
              created_at: c.created_at,
            })),
        )
      })
      .catch((err) => {
        if (err instanceof SessionExpiredError) return
        setLoadError(err instanceof Error ? err.message : 'Could not load messages.')
      })
  }, [slug, quote.quote_request_id])

  useEffect(() => {
    load()
  }, [load])

  if (!quote.quote_request_id) {
    return (
      <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
        Chat isn't available on this quote — please call or email instead.
      </p>
    )
  }
  if (loadError) {
    return (
      <p role="alert" className="mt-[var(--space-md)] text-[13.5px] text-[var(--accent-dark)]">
        {loadError}
      </p>
    )
  }
  if (messages === null) return <DocumentLoading label="Loading messages…" />

  return (
    <div className="mt-[var(--space-md)]">
      <ChatThread
        initialMessages={messages}
        onSend={async (body) => {
          if (!quote.quote_request_id) return {}
          await postCommunication(slug, quote.quote_request_id, body)
          // No synchronous reply on this channel — the team answers
          // asynchronously; refresh picks new messages up.
          load()
          return {}
        }}
      />
      <button
        type="button"
        onClick={load}
        className="mt-2 text-[12.5px] font-semibold text-[var(--muted)] underline underline-offset-2"
      >
        Check for new replies
      </button>
    </div>
  )
}

function QuoteDetail({ id }: { id: string }) {
  const { slug, config, sessionVersion } = usePortal()
  const [status, setStatus] = useState<'loading' | 'error' | 'loaded'>('loading')
  const [error, setError] = useState('')
  const [quote, setQuote] = useState<CustomerQuote | null>(null)
  const [panel, setPanel] = useState<'none' | 'accept' | 'decline' | 'discuss'>('none')
  const [actionPending, setActionPending] = useState(false)

  useEffect(() => {
    let cancelled = false
    listQuotes(slug)
      .then((data) => {
        if (cancelled) return
        setQuote(data.find((q) => q.id === id) ?? null)
        setStatus('loaded')
      })
      .catch((err) => {
        if (cancelled || err instanceof SessionExpiredError) return
        setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [slug, id, sessionVersion])

  if (status === 'loading') return <DocumentLoading label="Loading your quote…" />
  if (status === 'error') {
    return (
      <p role="alert" className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-4 text-[14px] leading-relaxed">
        {error}
      </p>
    )
  }
  if (!quote) {
    return (
      <p className="border-2 border-[var(--rule)] bg-[var(--paper-2)] p-5 text-[14px] text-[var(--muted)]">
        We couldn't find that quote. <Link to="/quotes" className="link-arrow">Back to your quotes</Link>
      </p>
    )
  }

  const vatPercent = Math.round(Number(quote.vat_rate) * 100)
  const actionable = quote.status === 'sent'

  async function handleDecline() {
    if (actionPending || !quote) return
    setActionPending(true)
    try {
      const updated = await rejectQuote(slug, quote.id)
      setQuote(updated)
      setPanel('none')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong — please try again.')
    } finally {
      setActionPending(false)
    }
  }

  return (
    <section className="border-2 border-[var(--ink)] bg-[var(--paper)]">
      <div className="px-6 py-[var(--space-lg)] md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-display text-[clamp(1.2rem,3vw,1.7rem)] font-extrabold uppercase leading-tight tracking-[0.02em]">
              {quote.title}
            </h2>
            <p className="mt-1 text-[13px] text-[var(--muted)]">
              {quote.sent_at && <>Sent {formatDate(quote.sent_at)}</>}
              {quote.sent_at && quote.valid_until && ' · '}
              {quote.valid_until && <>Valid until {formatDate(quote.valid_until)}</>}
            </p>
          </div>
          <StatusBadge status={quote.status} />
        </div>

        {quote.description && (
          <p className="mt-[var(--space-md)] whitespace-pre-line text-[14.5px] leading-relaxed">
            {quote.description}
          </p>
        )}

        {quote.status === 'approved' && (
          <p className="mt-[var(--space-md)] border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14px] font-semibold leading-relaxed text-[var(--ink-deep)]" role="status">
            Booking request sent — {config.name} will confirm your visit.
          </p>
        )}
        {quote.status === 'rejected' && (
          <p className="mt-[var(--space-md)] border-2 border-[var(--rule)] bg-[var(--paper-2)] p-4 text-[14px] leading-relaxed text-[var(--muted)]">
            You've declined this quote. Changed your mind? Message or call {config.name} below.
          </p>
        )}

        <table className="mt-[var(--space-lg)] w-full border-collapse text-[14px]">
          <thead>
            <tr className="border-b-2 border-[var(--ink)] text-left">
              <th className="py-2 pr-3 font-bold">Item</th>
              <th className="px-3 py-2 text-right font-bold">Qty</th>
              <th className="px-3 py-2 text-right font-bold">Unit price</th>
              <th className="py-2 pl-3 text-right font-bold">Total</th>
            </tr>
          </thead>
          <tbody>
            {quote.line_items.map((line) => (
              <tr key={line.id} className="border-b border-[var(--rule)]">
                <td className="py-2.5 pr-3 align-top">{line.description}</td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right align-top">
                  {Number(line.quantity)} {line.unit !== 'ea' ? line.unit : ''}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-right align-top">
                  {formatMoney('GBP', line.unit_price)}
                </td>
                <td className="whitespace-nowrap py-2.5 pl-3 text-right align-top">
                  {formatMoney('GBP', line.total)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="ml-auto mt-[var(--space-md)] w-full max-w-[280px] text-[14px]">
          <div className="flex justify-between py-1">
            <dt className="text-[var(--muted)]">Subtotal (ex VAT)</dt>
            <dd>{formatMoney('GBP', quote.subtotal)}</dd>
          </div>
          <div className="flex justify-between border-b border-[var(--rule)] py-1">
            <dt className="text-[var(--muted)]">VAT{vatPercent ? ` (${vatPercent}%)` : ''}</dt>
            <dd>{formatMoney('GBP', quote.vat_amount)}</dd>
          </div>
          <div className="flex justify-between py-2 text-[16px] font-extrabold">
            <dt>Total</dt>
            <dd>{formatMoney('GBP', quote.total)}</dd>
          </div>
        </dl>

        <StatusTimeline quote={quote} />

        {actionable && (
          <div className="mt-[var(--space-xl)] border-t-2 border-[var(--rule)] pt-[var(--space-lg)]">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setPanel(panel === 'accept' ? 'none' : 'accept')}
                className="chip chip--fill justify-center"
              >
                Accept quote
              </button>
              <button
                type="button"
                onClick={() => setPanel(panel === 'decline' ? 'none' : 'decline')}
                className="chip justify-center"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={() => setPanel(panel === 'discuss' ? 'none' : 'discuss')}
                className="chip justify-center"
              >
                Request changes / discuss
              </button>
            </div>

            {panel === 'accept' && (
              <AcceptPanel
                quote={quote}
                onDone={(updated) => {
                  setQuote(updated)
                  setPanel('none')
                }}
                onCancel={() => setPanel('none')}
              />
            )}
            {panel === 'decline' && (
              <div className="mt-[var(--space-md)] border-2 border-[var(--ink)] bg-[var(--paper-2)] p-5">
                <p className="text-[14px] font-semibold">Decline this quote?</p>
                <p className="mt-1 text-[13px] text-[var(--muted)]">
                  {config.name} will be notified. You can still message them afterwards.
                </p>
                <div className="mt-[var(--space-md)] flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleDecline}
                    disabled={actionPending}
                    className="chip justify-center disabled:opacity-50"
                  >
                    {actionPending ? 'Declining…' : 'Yes, decline'}
                  </button>
                  <button type="button" onClick={() => setPanel('none')} className="chip justify-center">
                    Keep quote
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {!actionable && panel !== 'discuss' && (
          <div className="mt-[var(--space-xl)] border-t-2 border-[var(--rule)] pt-[var(--space-lg)]">
            <button type="button" onClick={() => setPanel('discuss')} className="chip justify-center">
              Discuss this quote
            </button>
          </div>
        )}
        {panel === 'discuss' && <DiscussPanel quote={quote} />}

        <div className="mt-[var(--space-xl)] flex flex-wrap gap-2 border-t-2 border-[var(--rule)] pt-[var(--space-lg)]">
          {config.phone && (
            <a href={`tel:${config.phone}`} className="chip justify-center">
              Call {config.name}
            </a>
          )}
          {config.reply_email && (
            <a
              href={`mailto:${config.reply_email}?subject=${encodeURIComponent(`Re: your quote — ${quote.title}`)}`}
              className="chip justify-center"
            >
              Email us
            </a>
          )}
        </div>
      </div>
    </section>
  )
}

export default function PortalQuoteDetail() {
  const { config } = usePortal()
  const { id = '' } = useParams()
  usePageMeta(`Your quote — ${config.name}`, `Quote from ${config.name}.`)
  return (
    <PortalShell>
      <p className="mb-[var(--space-sm)] text-[13px]">
        <Link to="/quotes" className="link-arrow">
          ← All quotes
        </Link>
      </p>
      <RequireAuth>
        <QuoteDetail id={id} />
      </RequireAuth>
    </PortalShell>
  )
}
