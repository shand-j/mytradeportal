const ITEMS = [
  "AI quote drafting",
  "Plain-English intake",
  "Job booking",
  "One-touch invoicing",
  "Customer chat",
  "Calendar",
  "Guide prices",
  "VAT handled",
];

export function Marquee() {
  const row = [...ITEMS, ...ITEMS];
  return (
    <div className="marquee" aria-hidden>
      <div className="marquee-track">
        {row.map((item, i) => (
          <span key={i} className="marquee-item">
            <span className="marquee-dot" />
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
