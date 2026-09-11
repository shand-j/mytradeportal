import { useEffect } from 'react'
import Lenis from 'lenis'
import { useSmoothScroll } from '../hooks/useSmoothScroll'
import { usePageMeta } from '../hooks/usePageMeta'
import Nav from '../sections/Nav'
import Hero from '../sections/Hero'
import Marquee from '../sections/Marquee'
import TradesStrip from '../sections/TradesStrip'
import Statement from '../sections/Statement'
import Problem from '../sections/Problem'
import Showcase from '../sections/Showcase'
import VideoDemo from '../sections/VideoDemo'
import HowItWorks from '../sections/HowItWorks'
import Pricing from '../sections/Pricing'
import Testimonials from '../sections/Testimonials'
import FinalCta from '../sections/FinalCta'
import Footer from '../sections/Footer'

export default function Home() {
  useSmoothScroll()
  usePageMeta(
    'My Trade Portal — AI quotes & invoicing for UK electricians',
    'My Trade Portal is an AI-powered iOS app for UK electricians: draft guide-priced quotes in seconds, chat with customers, and send invoices — all under your own brand. In beta on TestFlight.',
  )

  /* Reveal-once: one IntersectionObserver adds .is-in to every .reveal */
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>('.reveal')
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-in')
            io.unobserve(e.target)
          }
        })
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    )
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [])

  /* Anchor navigation goes through Lenis so scroll stays smooth */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest<HTMLAnchorElement>('a[href^="#"]')
      if (!a) return
      const id = a.getAttribute('href')
      if (!id || id === '#') return
      const el = document.querySelector(id)
      if (!el) return
      e.preventDefault()
      const lenis = (window as unknown as { __lenis?: Lenis }).__lenis
      lenis?.scrollTo(el as HTMLElement, { offset: -70 })
    }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [])

  return (
    <main className="relative">
      <Nav />
      <Hero />
      <Marquee />
      <TradesStrip />
      <Statement />
      <Problem />
      <Showcase />
      <VideoDemo />
      <HowItWorks />
      <Pricing />
      <Testimonials />
      <FinalCta />
      <Footer />
    </main>
  )
}
