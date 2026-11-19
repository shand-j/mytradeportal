import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { AcceptInvitePanel } from '../portal/reset/AcceptInvitePanel'

export default function AcceptInvite() {
  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        <AcceptInvitePanel />
      </div>
      <Footer />
    </main>
  )
}
