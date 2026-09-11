import type { ReactNode } from 'react'

/** Realistic phone frame with dynamic island, status bar and home indicator. */
export default function PhoneFrame({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`relative rounded-[44px] bg-[#14181d] p-[10px] shadow-[0_40px_80px_-24px_rgba(0,0,0,0.4)] ${className}`}
    >
      {/* side buttons */}
      <div className="absolute -left-[2px] top-24 h-10 w-[3px] rounded-l bg-[#2b323a]" />
      <div className="absolute -left-[2px] top-40 h-14 w-[3px] rounded-l bg-[#2b323a]" />
      <div className="absolute -right-[2px] top-32 h-16 w-[3px] rounded-r bg-[#2b323a]" />
      <div className="relative aspect-[9/19.2] w-full overflow-hidden rounded-[34px] bg-[var(--cream)]">
        {/* status bar */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-center justify-between px-6 pt-3 text-[10px] font-semibold text-[var(--navy)]">
          <span>9:41</span>
          <div className="flex items-center gap-1">
            <svg width="14" height="10" viewBox="0 0 14 10" fill="currentColor" aria-hidden>
              <rect x="0" y="6" width="2.5" height="4" rx="0.5" />
              <rect x="3.8" y="4" width="2.5" height="6" rx="0.5" />
              <rect x="7.6" y="2" width="2.5" height="8" rx="0.5" />
              <rect x="11.4" y="0" width="2.5" height="10" rx="0.5" />
            </svg>
            <svg width="20" height="10" viewBox="0 0 22 11" fill="none" aria-hidden>
              <rect x="0.5" y="0.5" width="18" height="10" rx="3" stroke="currentColor" opacity="0.5" />
              <rect x="2" y="2" width="13" height="7" rx="1.5" fill="currentColor" />
              <rect x="20" y="3.5" width="2" height="4" rx="1" fill="currentColor" opacity="0.5" />
            </svg>
          </div>
        </div>
        {/* dynamic island */}
        <div className="absolute left-1/2 top-2.5 z-30 h-[22px] w-[86px] -translate-x-1/2 rounded-full bg-[#14181d]" />
        {children}
        {/* home indicator */}
        <div className="absolute bottom-1.5 left-1/2 z-30 h-1 w-24 -translate-x-1/2 rounded-full bg-[var(--navy)]/70" />
      </div>
    </div>
  )
}
