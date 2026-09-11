import { useEffect, useRef, useState } from 'react'

const JOBS = [
  'Consumer units',
  'EV chargers',
  'EICR testing',
  'Fuse boards',
  'Full rewires',
  'Outdoor power',
  'Fault finding',
  'Smart lighting',
]

const SET_MS = 2800
const SWAP_MS = 350

/** Job-types band — a fixed single line that rotates through the list:
 *  fade out, swap the set, fade back in. No scrolling (that felt cheap). */
export default function Marquee() {
  const [start, setStart] = useState(0)
  const [leaving, setLeaving] = useState(false)
  const [perView, setPerView] = useState(4)
  const timeoutRef = useRef<number | null>(null)

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const apply = () => setPerView(mq.matches ? 4 : 2)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => {
      setLeaving(true)
      timeoutRef.current = window.setTimeout(() => {
        setStart((s) => (s + perView) % JOBS.length)
        setLeaving(false)
      }, SWAP_MS)
    }, SET_MS)
    return () => {
      window.clearInterval(id)
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current)
    }
  }, [perView])

  const visible = Array.from({ length: perView }, (_, i) => JOBS[(start + i) % JOBS.length])

  return (
    <section aria-label="Job types covered" className="border-b-2 border-[var(--ink)] bg-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-md)] md:px-10">
        <div
          aria-live="off"
          className={`flex flex-nowrap items-baseline gap-x-[var(--space-lg)] overflow-hidden whitespace-nowrap transition-all duration-[350ms] ${
            leaving ? '-translate-y-1 opacity-0' : 'translate-y-0 opacity-100'
          }`}
          style={{ transitionTimingFunction: 'var(--ease)' }}
        >
          {visible.map((job, i) => (
            <span key={i} className="flex items-baseline gap-[var(--space-lg)]">
              <span className="whitespace-nowrap font-display text-[15px] font-bold uppercase tracking-[0.1em] text-[var(--paper-on-dark)]">
                {job}
              </span>
              <span className="font-display text-[15px] font-bold text-[var(--accent)]" aria-hidden>
                +
              </span>
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}
