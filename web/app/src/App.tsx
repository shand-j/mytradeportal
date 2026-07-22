import { Routes, Route } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { RouteErrorBoundary } from '@/components/error';
import { ProtectedRoute } from '@/lib/auth/ProtectedRoute';
import { Login } from '@/pages/login/Login';
import { Dashboard } from '@/pages/Dashboard';
import { Calendar } from '@/pages/Calendar';
import { QuotesList } from '@/pages/quotes/QuotesList';
import { QuoteDetail } from '@/pages/quotes/QuoteDetail';
import { JobsBoard } from '@/pages/jobs/JobsBoard';
import { JobDetail } from '@/pages/jobs/JobDetail';
import { CustomerDirectory } from '@/pages/customers/CustomerDirectory';
import { CustomerDetail } from '@/pages/customers/CustomerDetail';
import { InvoiceList } from '@/pages/invoices/InvoiceList';
import { InvoiceDetail } from '@/pages/invoices/InvoiceDetail';
import { Reviews } from '@/pages/Reviews';
import { AiInsights } from '@/pages/AiInsights';
import { Settings } from '@/pages/settings/Settings';

function safe(element: React.ReactNode) {
  return <RouteErrorBoundary>{element}</RouteErrorBoundary>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={safe(<Login />)} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route path="/" element={safe(<Dashboard />)} />
          <Route path="/calendar" element={safe(<Calendar />)} />
          <Route path="/calendar/:view" element={safe(<Calendar />)} />
          <Route path="/quotes" element={safe(<QuotesList />)} />
          <Route path="/quotes/:id" element={safe(<QuoteDetail />)} />
          <Route path="/jobs" element={safe(<JobsBoard />)} />
          <Route path="/jobs/:id" element={safe(<JobDetail />)} />
          <Route path="/customers" element={safe(<CustomerDirectory />)} />
          <Route path="/customers/:id" element={safe(<CustomerDetail />)} />
          <Route path="/invoices" element={safe(<InvoiceList />)} />
          <Route path="/invoices/:id" element={safe(<InvoiceDetail />)} />
          <Route path="/reviews" element={safe(<Reviews />)} />
          <Route path="/ai-insights" element={safe(<AiInsights />)} />
          <Route path="/settings" element={safe(<Settings />)} />
          <Route path="/settings/:tab" element={safe(<Settings />)} />
        </Route>
      </Route>
    </Routes>
  );
}
