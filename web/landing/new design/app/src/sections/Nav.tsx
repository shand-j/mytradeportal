import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import Logo from '../components/Logo'
import { TESTFLIGHT_URL } from '@/lib/site'

const LINKS = [
  ['The tour', '#features'],
  ['How it works', '#how'],
  ['Pricing', '#pricing'],
  ['Reviews', '#reviews'],
  ['Blog', '/blog'],
] as const

export default function Nav() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const onHome = pathname === '/'

  /** Anchor links only exist on Home; from other routes they deep-link back to it. */
  const resolveHref = (href: string) => (href.startsWith('#') && !onHome ? `/${href}` : href)

  return (
    <header className="sticky top-0 z-[var(--z-sticky)] border-b-2 border-[var(--ink)] bg-[var(--paper)]">
      <div className="mx-auto flex max-w-[1600px] items-center gap-6 px-6 py-3 md:px-10">
        <a
          href={onHome ? '#top' : '/'}
          className="flex items-center gap-3"
          onClick={() => setOpen(false)}
        >
          <Logo size={32} radius={0} className="shrink-0" />
          <span className="font-display text-[17px] font-extrabold uppercase tracking-[0.04em]">
            MyTradePortal
          </span>
        </a>

        <nav aria-label="Primary" className="ml-auto hidden md:block">
          <ul className="flex items-center gap-7">
            {LINKS.map(([label, href]) => (
              <li key={href}>
                {href.startsWith('/') ? (
                  <Link
                    to={href}
                    className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--ink)]/75 underline decoration-transparent decoration-2 underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--ink)] hover:decoration-[var(--accent)]"
                  >
                    {label}
                  </Link>
                ) : (
                  <a
                    href={resolveHref(href)}
                    className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--ink)]/75 underline decoration-transparent decoration-2 underline-offset-4 transition-colors duration-[length:var(--dur-micro)] hover:text-[var(--ink)] hover:decoration-[var(--accent)]"
                  >
                    {label}
                  </a>
                )}
              </li>
            ))}
          </ul>
        </nav>

        <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" className="chip chip--fill ml-auto hidden !min-h-[40px] md:ml-2 md:inline-flex">
          Join the beta
        </a>

        <button
          type="button"
          aria-label={open ? 'Close menu' : 'Open menu'}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="ml-auto flex h-11 w-11 flex-col items-center justify-center gap-[5px] border-1.5 border-[var(--ink)] md:hidden"
          style={{ borderWidth: '1.5px' }}
        >
          <span className={`h-[2px] w-5 bg-[var(--ink)] transition-transform duration-[length:var(--dur-short)] ${open ? 'translate-y-[7px] rotate-45' : ''}`} />
          <span className={`h-[2px] w-5 bg-[var(--ink)] transition-opacity duration-[length:var(--dur-micro)] ${open ? 'opacity-0' : ''}`} />
          <span className={`h-[2px] w-5 bg-[var(--ink)] transition-transform duration-[length:var(--dur-short)] ${open ? '-translate-y-[7px] -rotate-45' : ''}`} />
        </button>
      </div>

      {open && (
        <nav aria-label="Mobile" className="border-t border-[var(--rule)] md:hidden">
          <ul className="flex flex-col px-6 py-2">
            {LINKS.map(([label, href]) => (
              <li key={href} className="border-b border-[var(--rule)] last:border-0">
                {href.startsWith('/') ? (
                  <Link
                    to={href}
                    onClick={() => setOpen(false)}
                    className="block py-3.5 text-[14px] font-semibold uppercase tracking-[0.1em]"
                  >
                    {label}
                  </Link>
                ) : (
                  <a
                    href={resolveHref(href)}
                    onClick={() => setOpen(false)}
                    className="block py-3.5 text-[14px] font-semibold uppercase tracking-[0.1em]"
                  >
                    {label}
                  </a>
                )}
              </li>
            ))}
            <li className="py-3.5">
              <a href={TESTFLIGHT_URL} target="_blank" rel="noopener noreferrer" onClick={() => setOpen(false)} className="chip chip--fill w-full justify-center">
                Join the beta
              </a>
            </li>
          </ul>
        </nav>
      )}
    </header>
  )
}
