import HandUnderline from '../components/HandUnderline';

export default function Statement() {
  return (
    <section className="border-b-2 border-[var(--ink)]">
      <div className="mx-auto max-w-[1400px] px-5 py-[var(--space-3xl)] md:px-10 md:py-[var(--space-4xl)]">
        <p className="reveal max-w-[22ch] font-display text-[clamp(2rem,4.6vw,4.2rem)] leading-[1.02] font-extrabold tracking-[-0.02em] text-[var(--ink)]">
          The big firms have had this for years.{' '}
          <span className="text-[var(--muted)]">
            Now it's{' '}
            <span className="relative inline-block">
              your
              <HandUnderline className="absolute -bottom-1 left-0 h-[0.14em] w-full" />
            </span>{' '}
            turn.
          </span>
        </p>
        <p className="reveal mt-[var(--space-lg)] max-w-[46ch] text-[15.5px] leading-[1.75] text-[var(--muted)]" style={{ ['--i' as string]: 1 }}>
          For ten years, British Gas and the nationals have sent job links, taken bookings and collected reviews
          through their own apps — because they could afford the developers. MyTradePortal puts the same machine in
          your van, under your name, for the price of a tank of fuel.
        </p>
      </div>
    </section>
  );
}
