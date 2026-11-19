import { useEffect, useMemo, useState } from 'react'
import {
  fetchPublicQuoteAvailability,
  type PublicQuotePreference,
  type QuoteTimeWindow,
} from '../lib/public-docs-api'

/**
 * Availability-aware date picker for the public quote page: a calendar that
 * greys out the electrician's booked/closed days (coarse free/busy only —
 * no booking details are ever shown), lets the customer rank up to 3
 * date/time-window preferences, and falls back to a plain date input when
 * the availability fetch fails so acceptance is never blocked.
 */

const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const MAX_PICKS = 3

const CHOICE_LABELS = ['1st choice', '2nd choice', '3rd choice']

function formatDay(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

function formatHours(hours: number): string {
  if (hours >= 8 && hours % 8 === 0) {
    const days = hours / 8
    return `${days} working day${days > 1 ? 's' : ''}`
  }
  return `around ${hours} hour${hours === 1 ? '' : 's'}`
}

function TimeWindowChips({
  preference,
  onChange,
}: {
  preference: PublicQuotePreference
  onChange: (time: QuoteTimeWindow | undefined) => void
}) {
  const options: { value: QuoteTimeWindow | undefined; label: string }[] = [
    { value: undefined, label: 'Any time' },
    { value: 'morning', label: 'Morning' },
    { value: 'afternoon', label: 'Afternoon' },
  ]
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const active = preference.time === option.value
        return (
          <button
            key={option.label}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={`border-2 px-2.5 py-1 text-[12px] font-semibold ${
              active
                ? 'border-[var(--ink)] bg-[var(--ink)] text-white'
                : 'border-[var(--rule)] bg-[var(--paper)] text-[var(--ink)]'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function QuotePreferencesCalendar({
  token,
  selected,
  onChange,
}: {
  token: string
  selected: PublicQuotePreference[]
  onChange: (next: PublicQuotePreference[]) => void
}) {
  const [state, setState] = useState<'loading' | 'error' | 'loaded'>('loading')
  const [estimatedHours, setEstimatedHours] = useState<number | null>(null)
  const [days, setDays] = useState<{ date: string; status: string }[]>([])
  const [manualDate, setManualDate] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchPublicQuoteAvailability(token)
      .then((data) => {
        if (cancelled) return
        setDays(data.days)
        setEstimatedHours(data.estimated_hours)
        setState('loaded')
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const statusByDate = useMemo(() => new Map(days.map((d) => [d.date, d.status])), [days])

  // Pad the first row with blanks so the grid always starts on a Monday.
  const cells = useMemo(() => {
    if (days.length === 0) return []
    const first = new Date(`${days[0].date}T12:00:00`)
    const lead = (first.getDay() + 6) % 7
    return [...Array<string | null>(lead).fill(null), ...days.map((d) => d.date)]
  }, [days])

  const rankOf = (date: string) => selected.findIndex((p) => p.date === date)

  function toggle(date: string) {
    const existing = rankOf(date)
    if (existing >= 0) {
      onChange(selected.filter((p) => p.date !== date))
    } else if (selected.length < MAX_PICKS) {
      onChange([...selected, { date }])
    }
  }

  function setTime(date: string, time: QuoteTimeWindow | undefined) {
    onChange(selected.map((p) => (p.date === date ? { ...p, time } : p)))
  }

  return (
    <div className="mt-[var(--space-sm)]">
      {state === 'loaded' && estimatedHours != null && estimatedHours > 0 && (
        <p className="mb-[var(--space-sm)] text-[13px] text-[var(--muted)]">
          This visit is estimated to take {formatHours(estimatedHours)}.
        </p>
      )}

      {state === 'loading' && (
        <div className="flex items-center gap-3 py-2" role="status">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--rule)] border-t-[var(--ink)]" />
          <p className="text-[13px] text-[var(--muted)]">Checking the calendar…</p>
        </div>
      )}

      {state === 'loaded' && (
        <>
          <div
            className="grid grid-cols-7 gap-1"
            role="grid"
            aria-label="Pick up to 3 preferred dates"
          >
            {WEEKDAY_LABELS.map((label) => (
              <div
                key={label}
                className="pb-1 text-center text-[10.5px] font-bold uppercase tracking-[0.06em] text-[var(--muted)]"
              >
                {label}
              </div>
            ))}
            {cells.map((date, index) => {
              if (date === null) {
                return <div key={`blank-${index}`} aria-hidden />
              }
              const dayStatus = statusByDate.get(date) ?? 'closed'
              const selectable = dayStatus === 'available' || dayStatus === 'partial'
              const rank = rankOf(date)
              const isSelected = rank >= 0
              const dayNumber = Number(date.slice(-2))
              return (
                <button
                  key={date}
                  type="button"
                  role="gridcell"
                  disabled={!selectable && !isSelected}
                  aria-pressed={isSelected}
                  aria-label={`${formatDay(date)}${
                    dayStatus === 'partial'
                      ? ' — partly booked'
                      : dayStatus === 'busy'
                        ? ' — fully booked'
                        : dayStatus === 'closed'
                          ? ' — not a working day'
                          : ''
                  }${isSelected ? `, ${CHOICE_LABELS[rank]}` : ''}`}
                  onClick={() => toggle(date)}
                  className={`relative flex h-10 items-center justify-center border-2 text-[13px] font-semibold ${
                    isSelected
                      ? 'border-[var(--ink)] bg-[var(--brand,#0F1E26)] text-white'
                      : selectable
                        ? 'border-[var(--rule)] bg-[var(--paper)] hover:border-[var(--ink)]'
                        : 'cursor-not-allowed border-transparent text-[var(--muted)] opacity-40'
                  }`}
                >
                  {dayNumber}
                  {isSelected && (
                    <span className="absolute right-0.5 top-0.5 text-[9px] font-bold">
                      {rank + 1}
                    </span>
                  )}
                  {dayStatus === 'partial' && !isSelected && (
                    <span
                      aria-hidden
                      className="absolute bottom-1 h-1 w-1 rounded-full bg-amber-500"
                    />
                  )}
                </button>
              )
            })}
          </div>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--muted)]">
            <span aria-hidden className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />
            partly booked · greyed-out days are fully booked or not working days. Pick up to 3
            dates — numbered in the order you choose them.
          </p>
        </>
      )}

      {state === 'error' && (
        <>
          <p className="text-[12.5px] text-[var(--muted)]">
            Couldn't load the live calendar — pick any dates that suit you and{' '}
            your electrician will confirm.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={manualDate}
              min={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setManualDate(e.target.value)}
              aria-label="Pick a preferred date"
              className="border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-1.5 text-[13.5px] focus:outline-none"
            />
            <button
              type="button"
              disabled={
                !manualDate || selected.some((p) => p.date === manualDate) ||
                selected.length >= MAX_PICKS
              }
              onClick={() => {
                onChange([...selected, { date: manualDate }])
                setManualDate('')
              }}
              className="border-2 border-[var(--ink)] bg-[var(--paper)] px-3 py-1.5 text-[12.5px] font-bold uppercase tracking-[0.06em] disabled:opacity-40"
            >
              Add
            </button>
          </div>
        </>
      )}

      {selected.length > 0 && (
        <div className="mt-[var(--space-sm)] flex flex-col gap-2">
          {selected.map((preference, index) => (
            <div
              key={preference.date}
              className="flex flex-wrap items-center justify-between gap-2 border-2 border-[var(--rule)] bg-[var(--paper-2)] px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--muted)]">
                  {CHOICE_LABELS[index]}
                </span>
                <span className="text-[13.5px] font-semibold">{formatDay(preference.date)}</span>
                <button
                  type="button"
                  aria-label={`Remove ${formatDay(preference.date)}`}
                  onClick={() => toggle(preference.date)}
                  className="text-[14px] font-bold leading-none"
                >
                  ×
                </button>
              </div>
              <TimeWindowChips
                preference={preference}
                onChange={(time) => setTime(preference.date, time)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
