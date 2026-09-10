const FAQS = [
  {
    q: "Is it really free during beta?",
    a: "Yes. While the app is in TestFlight beta every plan is unlocked — no card, no subscription. When we launch, beta testers keep a discount as a thank-you.",
  },
  {
    q: "Which devices are supported?",
    a: "iPhone running iOS 16 or later, installed via TestFlight. Android and web are on the roadmap after the iOS launch.",
  },
  {
    q: "How does the AI quote drafting work?",
    a: "You describe the job in plain English. The AI matches your description against real cost-item data (starting with Screwfix pricing) and drafts priced line items, with its assumptions listed so you can check them before anything goes to the customer.",
  },
  {
    q: "Is my customer data safe?",
    a: "Each trade business gets its own isolated data space — no other tenant can see your customers, quotes or prices. Data is encrypted in transit and at rest.",
  },
  {
    q: "What happens when the beta ends?",
    a: "You'll pick a plan, keep everything you've set up, and keep the beta tester discount. Nothing is deleted and there's no automatic charge.",
  },
];

export function Faq() {
  return (
    <section className="section" id="faq">
      <div className="wrap wrap-narrow">
        <div className="section-head">
          <h2>Questions, answered.</h2>
        </div>
        <div className="faq-list">
          {FAQS.map((f) => (
            <details key={f.q} className="faq-item">
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
