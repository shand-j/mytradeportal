import { TESTFLIGHT_URL } from "@/lib/site";

export function Footer() {
  return (
    <footer className="footer">
      <div className="wrap footer-grid">
        <div className="footer-brand">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/mt-mark.svg" alt="" width={40} height={40} />
          <p className="footer-statement">
            The AI back office for UK trades.
          </p>
        </div>
        <nav className="footer-links" aria-label="Footer">
          <a href="/#features">Features</a>
          <a href="/#how-it-works">How it works</a>
          <a href="/#pricing">Pricing</a>
          <a href="/#faq">FAQ</a>
          <a href={TESTFLIGHT_URL}>Join the beta</a>
        </nav>
      </div>
      <div className="wrap footer-legal">
        <p>© {new Date().getFullYear()} My Trade Portal. All rights reserved.</p>
        <p>Made for the trades, not the office.</p>
      </div>
    </footer>
  );
}
