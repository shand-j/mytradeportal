import { MediaSlot } from "./media-slot";

type Feature = {
  eyebrow: string;
  title: string;
  body: string;
  poster: string;
  /** Drop the matching clip at public/media/<file> to activate video. */
  video?: string;
  points: string[];
};

const FEATURES: Feature[] = [
  {
    eyebrow: "Quote drafting",
    title: "Describe the job. Get a priced quote.",
    body: "Type what the customer told you — “new consumer unit, 12-way, garage sub-main” — and the AI drafts priced line items with assumptions and a confidence score. You review, tweak, and send.",
    poster: "/media/posters/01.jpg",
    video: "/media/feature-quotes.mp4",
    points: [
      "Guide-priced line items from Screwfix cost data",
      "Assumptions flagged so nothing is hidden",
      "Refine with AI or edit lines by hand",
    ],
  },
  {
    eyebrow: "Customer intake",
    title: "Customers request quotes in their own words.",
    body: "Your customer opens the app, answers a few questions about the property and the job, and the AI asks follow-ups if it needs more detail. No phone tag, no lost paperwork.",
    poster: "/media/posters/02.jpg",
    video: "/media/feature-intake.mp4",
    points: [
      "10-step wizard — photos included",
      "AI follow-up chat fills the gaps",
      "You get a ready-to-review draft",
    ],
  },
  {
    eyebrow: "Jobs & calendar",
    title: "Accepted quotes become booked jobs.",
    body: "Convert an accepted quote to a job in one tap. Preferred dates the customer picked come with it, and everything lands on your calendar.",
    poster: "/media/posters/04.jpg",
    video: "/media/feature-jobs.mp4",
    points: [
      "One-tap quote → job conversion",
      "Customer's preferred dates carried over",
      "Day, week and month views",
    ],
  },
  {
    eyebrow: "Invoicing",
    title: "Job done. Invoice sent. Paid.",
    body: "Finish the job, tap complete, and send a professional invoice with your branding — VAT handled correctly for registered and non-registered businesses.",
    poster: "/media/posters/05.jpg",
    video: "/media/feature-invoices.mp4",
    points: [
      "Invoice generated from the job",
      "Correct VAT for your registration status",
      "Track sent and paid at a glance",
    ],
  },
];

export function Features() {
  return (
    <section className="section" id="features">
      <div className="wrap">
        <div className="section-head">
          <h2>Everything between the phone call and the payment.</h2>
          <p>
            Four screens you'll use every day — each one cutting a slice of
            evening admin out of your week.
          </p>
        </div>
        <div className="feature-stack">
          {FEATURES.map((f, i) => (
            <article key={f.eyebrow} className={`feature ${i % 2 ? "feature-flip" : ""}`}>
              <div className="feature-media">
                <MediaSlot
                  posterSrc={f.poster}
                  videoSrc={f.video}
                  alt={`${f.title} — My Trade Portal on iPhone`}
                />
              </div>
              <div className="feature-copy">
                <p className="eyebrow">{f.eyebrow}</p>
                <h3>{f.title}</h3>
                <p className="feature-body">{f.body}</p>
                <ul className="feature-points">
                  {f.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
