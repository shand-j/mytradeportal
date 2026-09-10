import { TESTFLIGHT_URL } from "@/lib/site";

export function BetaCta() {
  return (
    <section className="section section-accent" id="beta">
      <div className="wrap beta-grid">
        <div>
          <p className="eyebrow eyebrow-on-accent">Beta — free access</p>
          <h2>Put the AI back office in your pocket.</h2>
          <p className="beta-sub">
            Join the TestFlight beta, run a real quote through it this week,
            and tell us what to fix. You&apos;ll keep the beta tester discount
            at launch.
          </p>
        </div>
        <div className="beta-actions">
          <a className="btn btn-ink" href={TESTFLIGHT_URL}>
            Join the beta on TestFlight
          </a>
          <p className="beta-note">iPhone · Free during beta · ~2 min setup</p>
        </div>
      </div>
    </section>
  );
}
