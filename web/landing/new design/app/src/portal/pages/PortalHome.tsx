import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { usePortal } from '../context'
import { PortalShell } from '../components/PortalShell'
import { ChatThread, type ChatMessage } from '../components/ChatThread'
import { usePageMeta } from '../../hooks/usePageMeta'
import {
  PortalApiError,
  postGuestMessage,
  submitQuoteRequest,
  uploadQuoteRequestImages,
  type EntryChannel,
  type QuoteRequestAck,
} from '../api'

type Phase = 'form' | 'submitting' | 'chat' | 'done'

/** Hard ceiling on the submitting view — the customer always lands somewhere. */
const SUBMIT_TIMEOUT_MS = 15_000
const MAX_PHOTOS = 5

interface GuestThread {
  requestId: string
  threadToken: string
  firstQuestion: string
}

export default function PortalHome() {
  const { slug, config } = usePortal()
  usePageMeta(`${config.name} — request a quote`, `Request a quote from ${config.name}.`)
  const [searchParams] = useSearchParams()

  const [phase, setPhase] = useState<Phase>('form')
  const [ack, setAck] = useState<QuoteRequestAck | null>(null)
  const [thread, setThread] = useState<GuestThread | null>(null)
  const [submitError, setSubmitError] = useState('')

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [photos, setPhotos] = useState<File[]>([])
  const [dates, setDates] = useState<string[]>([])
  const [newDate, setNewDate] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const photoPreviews = useMemo(
    () => photos.map((file) => ({ file, url: URL.createObjectURL(file) })),
    [photos],
  )

  const entryChannel: EntryChannel = searchParams.get('ch') === 'qr' ? 'qr' : 'direct'
  const canSubmit =
    name.trim().length > 0 && email.trim().length > 0 && description.trim().length >= 5

  function addPhotos(files: FileList | null) {
    if (!files) return
    setPhotos((prev) => [...prev, ...Array.from(files)].slice(0, MAX_PHOTOS))
  }

  async function runSubmission(): Promise<QuoteRequestAck> {
    let mediaUrls: string[] = []
    if (photos.length > 0) {
      try {
        mediaUrls = await uploadQuoteRequestImages(slug, photos)
      } catch (err) {
        // The public upload endpoint is new — if it isn't deployed yet,
        // submit without photos rather than blocking the request.
        const status = err instanceof PortalApiError ? err.status : 0
        if (status !== 404 && status !== 501 && status !== 405) throw err
      }
    }
    return submitQuoteRequest(slug, {
      name: name.trim(),
      email: email.trim(),
      phone: phone.trim() || undefined,
      category: category || undefined,
      description: description.trim(),
      media_urls: mediaUrls,
      preferred_dates: dates.map((date) => ({ date })),
      sync_check: true,
      entry_channel: entryChannel,
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit || phase === 'submitting') return
    setSubmitError('')
    setPhase('submitting')
    try {
      const result = await Promise.race([
        runSubmission(),
        new Promise<'timeout'>((resolve) => setTimeout(() => resolve('timeout'), SUBMIT_TIMEOUT_MS)),
      ])
      if (result === 'timeout') {
        // The request may still land server-side; the business has the
        // details either way, so move the customer to the done state.
        setPhase('done')
        return
      }
      setAck(result)
      if (result.ai_check?.status === 'questions' && result.ai_check.thread_token) {
        setThread({
          requestId: result.id,
          threadToken: result.ai_check.thread_token,
          firstQuestion:
            result.ai_check.question ?? 'Thanks — a couple of quick questions about the job.',
        })
        setPhase('chat')
      } else {
        setPhase('done')
      }
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : 'Something went wrong — please try again.',
      )
      setPhase('form')
    }
  }

  const initialThreadMessages: ChatMessage[] = thread
    ? [{ id: 'ai-first', role: 'ai', body: thread.firstQuestion }]
    : []

  return (
    <PortalShell>
      {/* Business-branded hero */}
      <section className="border-2 border-[var(--ink)] bg-[var(--paper)]">
        <div
          className="flex items-center gap-[var(--space-md)] border-b-2 border-[var(--ink)] px-6 py-6 md:px-10"
          style={{ backgroundColor: config.primary_color || '#0F1E26' }}
        >
          {config.logo_url && (
            <img
              src={config.logo_url}
              alt={`${config.name} logo`}
              className="h-14 w-14 border-2 border-white/40 bg-white object-contain"
            />
          )}
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display text-[clamp(1.4rem,4vw,2rem)] font-extrabold uppercase leading-tight tracking-[0.02em] text-white">
              {config.name}
            </h1>
            <p className="text-[12px] uppercase tracking-[0.1em] text-white/75">Request a quote</p>
          </div>
        </div>
        <div className="px-6 py-[var(--space-md)] md:px-10">
          {config.service_categories.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {config.service_categories.map((service) => (
                <li
                  key={service}
                  className="border-2 border-[var(--rule)] bg-[var(--paper-2)] px-2.5 py-1 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-[var(--muted)]"
                >
                  {service}
                </li>
              ))}
            </ul>
          )}
          {(config.phone || config.address) && (
            <p className="mt-[var(--space-sm)] text-[13px] text-[var(--muted)]">
              {config.phone && (
                <a href={`tel:${config.phone}`} className="font-semibold text-[var(--ink)] underline underline-offset-2">
                  {config.phone}
                </a>
              )}
              {config.phone && config.address && ' · '}
              {config.address}
            </p>
          )}
        </div>
      </section>

      {/* Quote-request form */}
      {(phase === 'form' || phase === 'submitting') && (
        <section className="mt-[var(--space-lg)] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
          <p className="spec-label text-[var(--muted)]">Tell us about the job</p>
          <form onSubmit={handleSubmit} className="mt-[var(--space-md)] space-y-[var(--space-md)]">
            <div className="grid gap-[var(--space-md)] sm:grid-cols-2">
              <div>
                <label htmlFor="qr-name" className="spec-label text-[var(--muted)]">
                  Your name *
                </label>
                <input
                  id="qr-name"
                  type="text"
                  required
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="qr-email" className="spec-label text-[var(--muted)]">
                  Email *
                </label>
                <input
                  id="qr-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                />
                <p className="mt-[var(--space-2xs)] text-[12px] text-[var(--muted)]">
                  Your quote is sent here — double-check it.
                </p>
              </div>
            </div>

            <div className="grid gap-[var(--space-md)] sm:grid-cols-2">
              <div>
                <label htmlFor="qr-phone" className="spec-label text-[var(--muted)]">
                  Phone
                </label>
                <input
                  id="qr-phone"
                  type="tel"
                  autoComplete="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                />
              </div>
              {config.service_categories.length > 0 && (
                <div>
                  <label htmlFor="qr-category" className="spec-label text-[var(--muted)]">
                    Type of work
                  </label>
                  <select
                    id="qr-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                  >
                    <option value="">Choose…</option>
                    {config.service_categories.map((service) => (
                      <option key={service} value={service}>
                        {service}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div>
              <label htmlFor="qr-description" className="spec-label text-[var(--muted)]">
                What needs doing? *
              </label>
              <textarea
                id="qr-description"
                required
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Fuse box keeps tripping when the kettle and shower run at the same time…"
                className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] leading-relaxed focus:outline-none"
              />
            </div>

            <div>
              <p className="spec-label text-[var(--muted)]">Photos (optional)</p>
              <div className="mt-[var(--space-2xs)] flex flex-wrap items-center gap-3">
                {photoPreviews.map(({ file, url }) => (
                  <div key={url} className="relative">
                    <img
                      src={url}
                      alt={file.name}
                      className="h-20 w-20 border-2 border-[var(--ink)] object-cover"
                    />
                    <button
                      type="button"
                      aria-label={`Remove ${file.name}`}
                      onClick={() => setPhotos((prev) => prev.filter((f) => f !== file))}
                      className="absolute -right-2 -top-2 flex h-5 w-5 items-center justify-center border-2 border-[var(--ink)] bg-[var(--paper)] text-[12px] font-bold leading-none"
                    >
                      ×
                    </button>
                  </div>
                ))}
                {photos.length < MAX_PHOTOS && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="flex h-20 w-20 items-center justify-center border-2 border-dashed border-[var(--rule)] text-[24px] text-[var(--muted)]"
                  >
                    +
                  </button>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                multiple
                hidden
                onChange={(e) => {
                  addPhotos(e.target.files)
                  e.target.value = ''
                }}
              />
            </div>

            <div>
              <p className="spec-label text-[var(--muted)]">Preferred visit dates (optional)</p>
              <div className="mt-[var(--space-2xs)] flex flex-wrap items-center gap-2">
                {dates.map((date) => (
                  <span
                    key={date}
                    className="inline-flex items-center gap-2 border-2 border-[var(--ink)] bg-[var(--paper-2)] px-2.5 py-1 text-[13px]"
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
            </div>

            {submitError && (
              <p
                role="alert"
                className="border-2 border-[var(--accent-dark)] bg-[var(--accent)]/15 p-3.5 text-[13.5px] leading-relaxed"
              >
                {submitError}
              </p>
            )}

            <button
              type="submit"
              disabled={!canSubmit || phase === 'submitting'}
              className="chip chip--fill w-full justify-center disabled:cursor-not-allowed disabled:opacity-40"
            >
              {phase === 'submitting' ? 'Sending your request…' : 'Request a quote'}
            </button>
            {phase === 'submitting' && (
              <p className="flex items-center gap-2 text-[12.5px] text-[var(--muted)]" role="status">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
                Checking the details with our assistant — usually a few seconds.
              </p>
            )}
          </form>
        </section>
      )}

      {/* AI triage thread */}
      {phase === 'chat' && thread && (
        <section className="mt-[var(--space-lg)]">
          <p className="spec-label mb-[var(--space-sm)] text-[var(--muted)]">
            A couple of quick questions
          </p>
          <ChatThread
            initialMessages={initialThreadMessages}
            onSend={async (body) => {
              const result = await postGuestMessage(thread.requestId, thread.threadToken, body)
              return { reply: result.ai_reply?.body, closed: result.closed }
            }}
            onEnd={() => setPhase('done')}
            endLabel="No more questions — done"
          />
        </section>
      )}

      {/* Done state */}
      {phase === 'done' && (
        <section className="mt-[var(--space-lg)] border-2 border-[var(--ink)] bg-[var(--paper)] p-6 md:p-10">
          <p className="spec-label text-[var(--muted)]">Request received</p>
          <div className="mt-[var(--space-md)]" role="status">
            <p className="border-2 border-[var(--ink)] bg-[var(--accent)] p-4 text-[14.5px] font-semibold leading-relaxed text-[var(--ink-deep)]">
              We're on it — you'll get an email when your quote is ready.
            </p>
            {ack?.reference && (
              <p className="mt-[var(--space-md)] text-[13.5px] text-[var(--muted)]">
                Your reference: <span className="font-mono font-semibold text-[var(--ink)]">{ack.reference}</span>
              </p>
            )}
            <p className="mt-[var(--space-md)] text-[13.5px] leading-relaxed text-[var(--muted)]">
              The email link also signs you in here, where you can follow your quote, chat with{' '}
              {config.name}, and pay the invoice when the work's done.
            </p>
            <button
              type="button"
              onClick={() => {
                setPhase('form')
                setAck(null)
                setThread(null)
                setDescription('')
                setPhotos([])
                setDates([])
              }}
              className="chip mt-[var(--space-lg)] justify-center"
            >
              Request another quote
            </button>
          </div>
        </section>
      )}
    </PortalShell>
  )
}
