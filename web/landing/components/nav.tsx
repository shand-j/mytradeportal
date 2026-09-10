import Link from "next/link";
import { TESTFLIGHT_URL } from "@/lib/site";

const LINKS = [
  { href: "/#features", label: "Features" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
];

export function Nav() {
  return (
    <header className="nav">
      <div className="nav-pill">
        <Link href="/#top" className="nav-brand" aria-label="My Trade Portal — home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/mt-mark.svg" alt="" width={28} height={28} />
          <span className="nav-wordmark">My Trade Portal</span>
        </Link>
        <nav className="nav-links" aria-label="Primary">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
        </nav>
        <a className="btn btn-primary nav-cta" href={TESTFLIGHT_URL}>
          Join the beta
        </a>
      </div>
    </header>
  );
}
