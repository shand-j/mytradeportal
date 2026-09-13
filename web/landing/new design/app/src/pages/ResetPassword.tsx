import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { ResetPasswordPanel } from '../portal/reset/ResetPasswordPanel'
import { isPortalMode } from '../portal/host'

export default function ResetPassword() {
  const portal = isPortalMode()
  return (
    <main className="relative flex min-h-screen flex-col">
      {!portal && <Nav />}
      <div className="flex flex-1 items-center justify-center px-5 py-[var(--space-2xl)]">
        <ResetPasswordPanel />
      </div>
      {!portal && <Footer />}
    </main>
  )
}
