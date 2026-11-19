import Nav from '../sections/Nav'
import Footer from '../sections/Footer'
import { PaymentsDashboardPanel } from '../payments/PaymentsDashboardPanel'

export default function PaymentsDashboard() {
  return (
    <main className="relative flex min-h-screen flex-col">
      <Nav />
      <div className="flex flex-1 justify-center px-5 py-[var(--space-2xl)]">
        <PaymentsDashboardPanel />
      </div>
      <Footer />
    </main>
  )
}
