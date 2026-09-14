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

/** Loose UK postcode shape — soft hint only, never blocks submission. */
const POSTCODE_RE = /^[A-Za-z]{1,2}\d[A-Za-z\d]?\s*\d[A-Za-z]{2}$/

/* Property profile options — mirror the mobile app's intake option sets. */
const PROPERTY_TYPES = [
  { key: 'detached', label: 'Detached' },
  { key: 'semi', label: 'Semi-detached' },
  { key: 'terrace', label: 'Terrace' },
  { key: 'bungalow', label: 'Bungalow' },
  { key: 'flat', label: 'Flat' },
]
const PROPERTY_AGES = [
  { key: 'pre_1930', label: 'Pre-1930' },
  { key: '1930-1960', label: '1930–1960' },
  { key: '1960-1980', label: '1960–1980' },
  { key: '1980-2000', label: '1980–2000' },
  { key: 'post_2000', label: 'Post-2000' },
  { key: 'not_sure', label: 'Not sure' },
]
const TENURES = [
  { key: 'owner', label: 'Owner' },
  { key: 'tenant', label: 'Tenant' },
  { key: 'landlord', label: 'Landlord' },
  { key: 'housing_assoc', label: 'Housing association' },
]
const FUSE_STYLES = [
  { key: 'modern_rcbo', label: 'Modern RCBO' },
  { key: 'rcd_split', label: 'RCD split-load' },
  { key: 'rewireable', label: 'Rewireable fuses' },
  { key: 'not_sure', label: 'Not sure' },
]
const KNOWN_ISSUES = [
  { key: 'tripping', label: 'Tripping' },
  { key: 'flickering', label: 'Flickering lights' },
  { key: 'smell', label: 'Burning smell' },
  { key: 'buzzing', label: 'Buzzing' },
  { key: 'dead_sockets', label: 'Dead sockets' },
]

function OptionChip({
  label,
  selected,
  onToggle,
}: {
  label: string
  selected: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onToggle}
      className={`min-h-[40px] border-2 px-3 py-1.5 text-[13px] font-semibold ${
        selected
          ? 'border-[var(--ink)] bg-[var(--accent)] text-[var(--ink-deep)]'
          : 'border-[var(--rule)] bg-[var(--paper)] text-[var(--ink)]'
      }`}
    >
      {label}
    </button>
  )
}

function ChipGroup({
  options,
  value,
  onChange,
}: {
  options: { key: string; label: string }[]
  value: string
  onChange: (key: string) => void
}) {
  return (
    <div className="mt-[var(--space-2xs)] flex flex-wrap gap-2">
      {options.map((option) => (
        <OptionChip
          key={option.key}
          label={option.label}
          selected={value === option.key}
          onToggle={() => onChange(value === option.key ? '' : option.key)}
        />
      ))}
    </div>
  )
}

function YesNoChips({
  value,
  onChange,
}: {
  value: boolean | null
  onChange: (value: boolean | null) => void
}) {
  return (
    <div className="mt-[var(--space-2xs)] flex flex-wrap gap-2">
      <OptionChip
        label="Yes"
        selected={value === true}
        onToggle={() => onChange(value === true ? null : true)}
      />
      <OptionChip
        label="No"
        selected={value === false}
        onToggle={() => onChange(value === false ? null : false)}
      />
    </div>
  )
}

function NumberSelect({
  id,
  label,
  value,
  max,
  min = 0,
  onChange,
}: {
  id: string
  label: string
  value: number | null
  max: number
  min?: number
  onChange: (value: number | null) => void
}) {
  return (
    <div>
      <label htmlFor={id} className="spec-label text-[var(--muted)]">
        {label}
      </label>
      <select
        id={id}
        value={value === null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
      >
        <option value="">—</option>
        {Array.from({ length: max - min + 1 }, (_, i) => min + i).map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
    </div>
  )
}

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
  const [address, setAddress] = useState('')
  const [postcode, setPostcode] = useState('')
  const [category, setCategory] = useState('')
  const [description, setDescription] = useState('')
  const [photos, setPhotos] = useState<File[]>([])
  const [dates, setDates] = useState<string[]>([])
  const [newDate, setNewDate] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [propertyOpen, setPropertyOpen] = useState(false)
  const [propType, setPropType] = useState('')
  const [propAge, setPropAge] = useState('')
  const [bedrooms, setBedrooms] = useState<number | null>(null)
  const [receptions, setReceptions] = useState<number | null>(null)
  const [floors, setFloors] = useState<number | null>(null)
  const [tenure, setTenure] = useState('')
  const [flatAccess, setFlatAccess] = useState<boolean | null>(null)
  const [parking, setParking] = useState<boolean | null>(null)
  const [fuseBoardStyle, setFuseBoardStyle] = useState('')
  const [knownIssues, setKnownIssues] = useState<string[]>([])

  const photoPreviews = useMemo(
    () => photos.map((file) => ({ file, url: URL.createObjectURL(file) })),
    [photos],
  )

  const entryChannel: EntryChannel = searchParams.get('ch') === 'qr' ? 'qr' : 'direct'
  const canSubmit =
    name.trim().length > 0 && email.trim().length > 0 && description.trim().length >= 5

  const postcodeLooksOff = postcode.trim().length > 0 && !POSTCODE_RE.test(postcode.trim())

  /** Only the property fields the customer actually answered. */
  function buildPropertyProfile(): Record<string, unknown> {
    const property: Record<string, unknown> = {}
    if (propType) property.type = propType
    if (propAge) property.age = propAge
    if (bedrooms !== null) property.bedrooms = bedrooms
    if (receptions !== null) property.receptions = receptions
    if (floors !== null) property.floors = floors
    if (tenure) property.tenure = tenure
    if (propType === 'flat' && flatAccess !== null) property.flatAccess = flatAccess
    if (parking !== null) property.parking = parking
    if (fuseBoardStyle) property.fuseBoardStyle = fuseBoardStyle
    if (knownIssues.length > 0) property.knownIssues = knownIssues
    return property
  }

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
    const property = buildPropertyProfile()
    return submitQuoteRequest(slug, {
      name: name.trim(),
      email: email.trim(),
      phone: phone.trim() || undefined,
      address: address.trim() || undefined,
      postcode: postcode.trim() || undefined,
      category: category || undefined,
      description: description.trim(),
      media_urls: mediaUrls,
      preferred_dates: dates.map((date) => ({ date })),
      sync_check: true,
      entry_channel: entryChannel,
      structured_data: Object.keys(property).length > 0 ? { property } : undefined,
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

            <div className="grid gap-[var(--space-md)] sm:grid-cols-2">
              <div>
                <label htmlFor="qr-address" className="spec-label text-[var(--muted)]">
                  Address
                </label>
                <input
                  id="qr-address"
                  type="text"
                  autoComplete="address-line1"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="House number and street"
                  className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="qr-postcode" className="spec-label text-[var(--muted)]">
                  Postcode
                </label>
                <input
                  id="qr-postcode"
                  type="text"
                  autoComplete="postal-code"
                  value={postcode}
                  onChange={(e) => setPostcode(e.target.value)}
                  placeholder="e.g. SW1A 1AA"
                  className="mt-[var(--space-2xs)] w-full border-2 border-[var(--ink)] bg-[var(--paper)] px-3.5 py-2.5 text-[15px] uppercase focus:outline-none"
                />
                {postcodeLooksOff && (
                  <p className="mt-[var(--space-2xs)] text-[12px] text-[var(--accent-dark)]">
                    That doesn't look like a UK postcode — worth a double-check.
                  </p>
                )}
              </div>
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

            <div className="border-2 border-[var(--rule)]">
              <button
                type="button"
                aria-expanded={propertyOpen}
                aria-controls="qr-property-panel"
                onClick={() => setPropertyOpen((open) => !open)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
              >
                <span>
                  <span className="spec-label block text-[var(--ink)]">About your property</span>
                  <span className="mt-1 block text-[12px] normal-case tracking-normal text-[var(--muted)]">
                    Optional — helps us quote faster and more accurately.
                  </span>
                </span>
                <span aria-hidden className="text-[18px] font-bold text-[var(--muted)]">
                  {propertyOpen ? '−' : '+'}
                </span>
              </button>
              {propertyOpen && (
                <div
                  id="qr-property-panel"
                  className="space-y-[var(--space-md)] border-t-2 border-[var(--rule)] px-4 py-[var(--space-md)]"
                >
                  <div>
                    <p className="spec-label text-[var(--muted)]">Property type</p>
                    <ChipGroup options={PROPERTY_TYPES} value={propType} onChange={setPropType} />
                  </div>

                  <div>
                    <p className="spec-label text-[var(--muted)]">Property age</p>
                    <ChipGroup options={PROPERTY_AGES} value={propAge} onChange={setPropAge} />
                  </div>

                  <div className="grid grid-cols-3 gap-[var(--space-sm)]">
                    <NumberSelect
                      id="qr-bedrooms"
                      label="Bedrooms"
                      value={bedrooms}
                      max={10}
                      onChange={setBedrooms}
                    />
                    <NumberSelect
                      id="qr-receptions"
                      label="Receptions"
                      value={receptions}
                      max={10}
                      onChange={setReceptions}
                    />
                    <NumberSelect
                      id="qr-floors"
                      label="Floors"
                      value={floors}
                      min={1}
                      max={5}
                      onChange={setFloors}
                    />
                  </div>

                  <div>
                    <p className="spec-label text-[var(--muted)]">You are the…</p>
                    <ChipGroup options={TENURES} value={tenure} onChange={setTenure} />
                  </div>

                  {propType === 'flat' && (
                    <div>
                      <p className="spec-label text-[var(--muted)]">Lift access?</p>
                      <YesNoChips value={flatAccess} onChange={setFlatAccess} />
                    </div>
                  )}

                  <div>
                    <p className="spec-label text-[var(--muted)]">Van parking available?</p>
                    <YesNoChips value={parking} onChange={setParking} />
                  </div>

                  <div>
                    <p className="spec-label text-[var(--muted)]">Fuse board style</p>
                    <ChipGroup
                      options={FUSE_STYLES}
                      value={fuseBoardStyle}
                      onChange={setFuseBoardStyle}
                    />
                  </div>

                  <div>
                    <p className="spec-label text-[var(--muted)]">Anything odd? (select any)</p>
                    <div className="mt-[var(--space-2xs)] flex flex-wrap gap-2">
                      {KNOWN_ISSUES.map((issue) => (
                        <OptionChip
                          key={issue.key}
                          label={issue.label}
                          selected={knownIssues.includes(issue.key)}
                          onToggle={() =>
                            setKnownIssues((prev) =>
                              prev.includes(issue.key)
                                ? prev.filter((k) => k !== issue.key)
                                : [...prev, issue.key],
                            )
                          }
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
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
