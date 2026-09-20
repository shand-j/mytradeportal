import { useMemo } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import Home from './pages/Home'
import ResetPassword from './pages/ResetPassword'
import AcceptInvite from './pages/AcceptInvite'
import ViewQuote from './pages/ViewQuote'
import ViewInvoice from './pages/ViewInvoice'
import PayInvoice from './pages/PayInvoice'
import FairUse from './pages/FairUse'
import StripeBounce from './pages/StripeBounce'
import BlogIndex from './pages/blog/BlogIndex'
import BlogPost from './pages/blog/BlogPost'
import HelpIndex from './pages/help/HelpIndex'
import HelpArticle from './pages/help/HelpArticle'
import { resolvePortalSlug } from './portal/host'
import { PortalProvider } from './portal/PortalProvider'
import PortalHome from './portal/pages/PortalHome'
import PortalMagicAuth from './portal/pages/PortalMagicAuth'
import PortalQuotes from './portal/pages/PortalQuotes'
import PortalQuoteDetail from './portal/pages/PortalQuoteDetail'
import PortalInvoices from './portal/pages/PortalInvoices'
import PortalInvoiceDetail from './portal/pages/PortalInvoiceDetail'
import PortalResetPassword from './portal/pages/PortalResetPassword'
import PortalClaim from './portal/pages/PortalClaim'
import CodeEntryPage from './portal/pages/CodeEntryPage'

export default function App() {
  // Tenant subdomains serve the customer portal from this same bundle;
  // www/apex/localhost serve the marketing site.
  const portalSlug = useMemo(() => resolvePortalSlug(), [])

  if (portalSlug) {
    return (
      <PortalProvider slug={portalSlug}>
        <Routes>
          <Route path="/" element={<PortalHome />} />
          <Route path="/auth/magic" element={<PortalMagicAuth />} />
          <Route path="/claim" element={<PortalClaim />} />
          <Route path="/quotes" element={<PortalQuotes />} />
          <Route path="/quotes/:id" element={<PortalQuoteDetail />} />
          <Route path="/invoices" element={<PortalInvoices />} />
          <Route path="/invoices/:id" element={<PortalInvoiceDetail />} />
          <Route path="/reset-password" element={<PortalResetPassword />} />
          {/* Secure token pages work on tenant subdomains too. */}
          <Route path="/quote/:token" element={<ViewQuote />} />
          <Route path="/invoice/:token" element={<ViewInvoice />} />
          <Route path="/pay/:token" element={<PayInvoice />} />
          <Route path="/fair-use" element={<FairUse />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </PortalProvider>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/code" element={<CodeEntryPage />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route path="/quote/:token" element={<ViewQuote />} />
      <Route path="/invoice/:token" element={<ViewInvoice />} />
      <Route path="/pay/:token" element={<PayInvoice />} />
      <Route path="/fair-use" element={<FairUse />} />
      <Route path="/payments/stripe-bounce" element={<StripeBounce />} />
      <Route path="/blog" element={<BlogIndex />} />
      <Route path="/blog/:slug" element={<BlogPost />} />
      <Route path="/help" element={<HelpIndex />} />
      <Route path="/help/:slug" element={<HelpArticle />} />
    </Routes>
  )
}
