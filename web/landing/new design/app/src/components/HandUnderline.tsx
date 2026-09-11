/**
 * Hand-drawn amber underline with an organic wobble.
 * Add class "drawn" (via ScrollTrigger) to run the draw animation.
 */
export default function HandUnderline({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 220 14"
      fill="none"
      aria-hidden
      className={`hand-underline ${className}`}
      preserveAspectRatio="none"
    >
      <path
        d="M3 9.5 C 30 4, 55 11, 84 7.5 S 140 3.5, 168 8 S 205 10.5, 217 6.5"
        stroke="var(--amber)"
        strokeWidth="5"
        strokeLinecap="round"
      />
    </svg>
  )
}
