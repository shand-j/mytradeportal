import type { ReactNode } from 'react'

/**
 * Pill button whose fill rises from the bottom on hover.
 * `tone="navy"` for beige sections, `tone="amber"` for navy sections.
 */
export default function PillButton({
  children,
  tone = 'navy',
  href = '#',
  className = '',
}: {
  children: ReactNode
  tone?: 'navy' | 'amber' | 'outline'
  href?: string
  className?: string
}) {
  const base =
    'group relative inline-flex items-center gap-2 overflow-hidden rounded-full px-7 py-3.5 font-display text-[15px] font-semibold uppercase tracking-[0.14em] transition-colors duration-300'
  const tones: Record<string, string> = {
    navy: 'bg-[var(--navy)] text-[var(--cream)]',
    amber: 'bg-[var(--amber)] text-[var(--navy-ink)]',
    outline:
      'border border-[var(--navy)]/40 text-[var(--navy)] hover:text-[var(--cream)]',
  }
  const fill =
    tone === 'amber'
      ? 'bg-[var(--navy-ink)]'
      : tone === 'outline'
        ? 'bg-[var(--navy)]'
        : 'bg-[var(--amber)]'

  return (
    <a href={href} data-cursor className={`${base} ${tones[tone]} ${className}`}>
      <span
        aria-hidden
        className={`absolute inset-x-0 bottom-0 h-0 ${fill} transition-[height] duration-300 ease-out group-hover:h-full`}
      />
      <span
        className={`relative z-10 transition-colors duration-300 ${
          tone === 'amber' ? 'group-hover:text-[var(--amber)]' : tone === 'navy' ? 'group-hover:text-[var(--navy-ink)]' : ''
        }`}
      >
        {children}
      </span>
    </a>
  )
}
