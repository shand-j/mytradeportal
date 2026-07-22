import { useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Calendar, FileText, Wrench, Users, Receipt, Star,
  Sparkles, Settings, ChevronRight, Zap, Phone,
} from 'lucide-react';
import type { UserRole } from '@/types';
import { useUiStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { authService } from '@/lib/api/auth';
import { useQuotes, useInvoices } from '@/lib/api/hooks';

const navItems: Array<{
  to: string;
  icon: typeof LayoutDashboard;
  label: string;
  badge?: string;
  roles?: UserRole[];
}> = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/calendar', icon: Calendar, label: 'Calendar' },
  { to: '/quotes', icon: FileText, label: 'Quotes', badge: 'pendingQuotes' },
  { to: '/jobs', icon: Wrench, label: 'Jobs' },
  { to: '/customers', icon: Users, label: 'Customers' },
  { to: '/invoices', icon: Receipt, label: 'Invoices', badge: 'overdueInvoices' },
  { to: '/reviews', icon: Star, label: 'Reviews' },
  { to: '/ai-insights', icon: Sparkles, label: 'AI Insights', roles: ['admin', 'manager'] },
  { to: '/settings', icon: Settings, label: 'Settings', roles: ['admin'] },
];

export function Sidebar() {
  const sidebarCollapsed = useUiStore(s => s.sidebarCollapsed);
  const toggleSidebar = useUiStore(s => s.toggleSidebar);
  const setSidebarCollapsed = useUiStore(s => s.setSidebarCollapsed);
  const location = useLocation();
  const navigate = useNavigate();
  const { data: quotes } = useQuotes();
  const { data: invoices } = useInvoices();
  const currentUser = useAuthStore(s => s.user);
  const logoutUser = useAuthStore(s => s.logout);

  useEffect(() => {
    const mql = window.matchMedia('(max-width: 768px)');
    const handle = (e: MediaQueryListEvent | MediaQueryList) => setSidebarCollapsed(e.matches);
    handle(mql);
    mql.addEventListener('change', handle);
    return () => mql.removeEventListener('change', handle);
  }, [setSidebarCollapsed]);

  const handleLogout = async () => {
    try {
      await authService.logout();
    } finally {
      logoutUser();
      navigate('/login', { replace: true });
    }
  };

  const getBadge = (key?: string) => {
    if (key === 'pendingQuotes') {
      const count = (quotes ?? []).filter(q => q.status === 'sent').length;
      return count > 0 ? count : null;
    }
    if (key === 'overdueInvoices') {
      const count = (invoices ?? []).filter(i => i.status === 'overdue').length;
      return count > 0 ? count : null;
    }
    return null;
  };

  const isActivePath = (to: string) => {
    if (to === '/') return location.pathname === '/';
    return location.pathname.startsWith(to);
  };

  return (
    <aside
      className={`flex flex-col h-full bg-[#F8F7F4] border-r border-[#E7E5E4] transition-all duration-300 ${
        sidebarCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Logo */}
      <div className={`flex items-center gap-3 px-4 pt-5 pb-6 ${sidebarCollapsed ? 'justify-center' : ''}`}>
        <div className="w-8 h-8 rounded-lg bg-[#D4650A] flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-white" />
        </div>
        {!sidebarCollapsed && (
          <div className="min-w-0">
            <div className="text-sm font-semibold text-[#1C1917] truncate">mytradeportal</div>
            <div className="text-xs text-[#78716C] truncate">Watts Electrical</div>
          </div>
        )}
      </div>

      {/* Voice Agent Promo */}
      {!sidebarCollapsed && (
        <div className="mx-3 mb-3 p-3 rounded-lg bg-[#1C1917] border border-[#2A2A2A]">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-full bg-[#D4650A] flex items-center justify-center">
              <Phone className="w-3 h-3 text-white" />
            </div>
            <span className="text-[11px] font-semibold text-white uppercase tracking-[0.05em]">Voice AI</span>
          </div>
          <p className="text-[11px] text-[#A8A29E] mb-2">AI answers calls, generates quotes, books jobs</p>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-[#333] rounded-full overflow-hidden">
              <div className="h-full bg-[#16A34A] rounded-full" style={{ width: '92%' }} />
            </div>
            <span className="text-[10px] text-[#16A34A] font-semibold">92%</span>
          </div>
          <div className="text-[10px] text-[#78716C] mt-1">resolution rate · 48 calls today</div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto">
        {navItems
          .filter((item) => !item.roles || (currentUser && item.roles.includes(currentUser.role)))
          .map((item) => {
          const active = isActivePath(item.to);
          const badge = getBadge(item.badge);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 h-10 px-3 rounded-lg transition-colors duration-150 ${
                active
                  ? 'bg-[#FFF7ED] text-[#D4650A]'
                  : 'text-[#57534E] hover:bg-[#F5F4F0] hover:text-[#1C1917]'
              } ${sidebarCollapsed ? 'justify-center' : ''}`}
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!sidebarCollapsed && (
                <>
                  <span className="text-xs font-medium uppercase tracking-[0.05em] flex-1 truncate">
                    {item.label}
                  </span>
                  {badge !== null && (
                    <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-[#D4650A] text-white text-[11px] font-semibold">
                      {badge}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div className="px-2 pb-4 pt-2 border-t border-[#F0EFEA]">
        <button
          onClick={toggleSidebar}
          className={`flex items-center gap-3 h-10 px-3 rounded-lg text-[#57534E] hover:bg-[#F5F4F0] transition-colors w-full ${
            sidebarCollapsed ? 'justify-center' : ''
          }`}
          title="Collapse sidebar"
        >
          <ChevronRight className={`w-5 h-5 flex-shrink-0 transition-transform duration-300 ${sidebarCollapsed ? '' : 'rotate-180'}`} />
          {!sidebarCollapsed && <span className="text-xs font-medium uppercase tracking-[0.05em]">Collapse</span>}
        </button>

        {!sidebarCollapsed && currentUser && (
          <div className="flex items-center gap-3 mt-2 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-[#D4650A] flex items-center justify-center text-white text-xs font-semibold">
              {currentUser.fullName.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-[#1C1917] truncate">
                {currentUser.fullName}
              </div>
              <div className="text-[11px] text-[#78716C] capitalize">
                {currentUser.role}
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="text-[11px] text-[#D4650A] hover:underline"
              title="Sign out"
            >
              Logout
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
