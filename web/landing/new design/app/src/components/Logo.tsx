/**
 * MT monogram — vector-traced from the production iOS app icon
 * (mtp-icon-ios-1024.png). Slate-ink square optional; mark itself
 * is hi-vis yellow.
 */
export default function Logo({
  size = 32,
  withBadge = true,
  radius = 180,
  className = '',
}: {
  size?: number
  withBadge?: boolean
  radius?: number
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 1024 1024"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="MyTradePortal logo"
    >
      {withBadge && <rect width="1024" height="1024" rx={radius} fill="var(--navy)" />}
      <g fill="var(--amber)">
        <path d="M527,237 L431,333 L431,471 L572,400 L612,400 L613,786 L760,786 L760,401 L851,400 L851,237 Z" />
        <path d="M172,237 L172,786 L311,786 L311,516 L399,602 L399,324 L312,237 Z" />
        <path d="M431,601 L431,770 L392,786 L544,786 L516,770 L516,602 Z" />
      </g>
    </svg>
  )
}
