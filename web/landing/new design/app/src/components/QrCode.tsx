/**
 * Decorative QR-style tile — deterministic pseudo-random module grid with
 * the three finder squares, so it reads as a real code at a glance.
 */
export default function QrCode({ size = 84, className = '' }: { size?: number; className?: string }) {
  const n = 21
  const cell = 100 / n
  const inFinder = (x: number, y: number) =>
    (x < 7 && y < 7) || (x >= n - 7 && y < 7) || (x < 7 && y >= n - 7)

  let seed = 42
  const rand = () => {
    seed = (seed * 16807) % 2147483647
    return seed / 2147483647
  }

  const cells: React.ReactNode[] = []
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      if (inFinder(x, y)) continue
      if (rand() > 0.52) {
        cells.push(
          <rect
            key={`${x}-${y}`}
            x={x * cell}
            y={y * cell}
            width={cell}
            height={cell}
            fill="var(--navy)"
          />,
        )
      }
    }
  }

  const finder = (fx: number, fy: number, key: string) => (
    <g key={key}>
      <rect x={fx * cell} y={fy * cell} width={7 * cell} height={7 * cell} fill="var(--navy)" />
      <rect
        x={(fx + 1) * cell}
        y={(fy + 1) * cell}
        width={5 * cell}
        height={5 * cell}
        fill="var(--cream)"
      />
      <rect
        x={(fx + 2) * cell}
        y={(fy + 2) * cell}
        width={3 * cell}
        height={3 * cell}
        fill="var(--navy)"
      />
    </g>
  )

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="QR code to add the demo app"
    >
      <rect width="100" height="100" fill="var(--cream)" />
      {cells}
      {finder(0, 0, 'a')}
      {finder(n - 7, 0, 'b')}
      {finder(0, n - 7, 'c')}
    </svg>
  )
}
