import { TESTFLIGHT_URL } from "@/lib/site";
import { MediaSlot } from "./media-slot";

/**
 * Hero — headline under 50 chars, typographic-led, with the hero video slot.
 * Drop the AI-generated hero footage at public/media/hero.mp4 to activate.
 */
export function Hero() {
  return (
    <section className="hero" id="top">
      <div className="wrap hero-grid">
        <div className="hero-copy">
          <p className="eyebrow">For UK electricians &amp; trades</p>
          <h1>Quotes to invoices, minus the paperwork.</h1>
          <p className="hero-sub">
            My Trade Portal drafts guide-priced quotes from a plain-English job
            description, books the work, and sends the invoice — all from your
            phone. AI does the admin; you do the job.
          </p>
          <div className="hero-actions">
            <a className="btn btn-primary" href={TESTFLIGHT_URL}>
              Join the iOS beta
            </a>
            <a className="btn btn-outline" href="#features">
              See it in action
            </a>
          </div>
          <p className="hero-note">
            Free during beta · iPhone (TestFlight) · No card required
          </p>
        </div>
        <div className="hero-media">
          <MediaSlot
            posterSrc="/media/posters/01.jpg"
            videoSrc="/media/hero.mp4"
            alt="My Trade Portal AI quote review screen on iPhone"
          />
        </div>
      </div>
    </section>
  );
}
