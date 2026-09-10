const STEPS = [
  {
    n: "01",
    title: "Say it plainly",
    body: "Type the job as the customer described it, or let them request it in the app themselves.",
  },
  {
    n: "02",
    title: "Review the draft",
    body: "AI prices the work with flagged assumptions. Check it, adjust anything, send it.",
  },
  {
    n: "03",
    title: "Book, do, invoice",
    body: "Acceptance becomes a booked job; completion becomes an invoice. One flow, no re-typing.",
  },
];

export function HowItWorks() {
  return (
    <section className="section section-ink" id="how-it-works">
      <div className="wrap">
        <div className="section-head">
          <h2>How it works</h2>
          <p>Three steps, one app, no spreadsheets.</p>
        </div>
        <ol className="steps">
          {STEPS.map((s) => (
            <li key={s.n} className="step">
              <span className="step-n" aria-hidden>
                {s.n}
              </span>
              <h3>{s.title}</h3>
              <p>{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
