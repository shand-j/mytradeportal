import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { SubscribePanel } from '../subscribe/SubscribePanel'

export default function Subscribe() {
  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        <SubscribePanel />
      </div>
      <Footer />
    </main>
  )
}
