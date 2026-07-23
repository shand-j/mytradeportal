import { Search, Bell, Plus, RefreshCw, Phone } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useUiStore } from '@/stores/uiStore';
import { useFeatureFlags } from '@/lib/api/hooks';
import { formatDistanceToNow } from 'date-fns';
import type { Notification } from '@/types';

export function TopBar() {
  const pageTitle = useUiStore(s => s.currentPageTitle);
  const notificationOpen = useUiStore(s => s.notificationOpen);
  const setNotificationOpen = useUiStore(s => s.setNotificationOpen);
  const { data: featureFlags } = useFeatureFlags();
  // Voice AI is not yet implemented; the button stays hidden until the
  // `voice_ai_insights` feature flag is enabled in Railway.
  const voiceAiEnabled = featureFlags?.voiceAiInsights === true;
  const [notifications] = useState<Notification[]>([]);
  const unreadCount = notifications.filter(n => !n.read).length;
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-10 h-16 flex items-center justify-between px-4 sm:px-6 bg-[#F8F7F4]/80 backdrop-blur-xl border-b border-[#E7E5E4] transition-shadow duration-200 ${
        scrolled ? 'shadow-[0_1px_6px_rgba(28,25,23,0.06)]' : ''
      }`}
    >
      <div>
        <div className="text-xl font-semibold text-[#1C1917]">{pageTitle}</div>
      </div>

      <div className="flex items-center gap-2">
        <button className="h-9 w-9 flex items-center justify-center rounded-lg text-[#57534E] hover:bg-[#F5F4F0] transition-colors">
          <Search className="w-[18px] h-[18px]" />
        </button>

        <button className="h-9 w-9 flex items-center justify-center rounded-lg text-[#57534E] hover:bg-[#F5F4F0] transition-colors">
          <RefreshCw className="w-[18px] h-[18px]" />
        </button>
        {voiceAiEnabled && (
        <button className="h-9 w-9 flex items-center justify-center rounded-lg text-[#7C3AED] hover:bg-[#F5F3FF] transition-colors relative" title="Voice AI Agent">
          <Phone className="w-[18px] h-[18px]" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#16A34A]" />
        </button>
        )}

        <div className="relative">
          <button
            aria-label="Notifications"
            onClick={() => setNotificationOpen(!notificationOpen)}
            className="h-9 w-9 flex items-center justify-center rounded-lg text-[#57534E] hover:bg-[#F5F4F0] transition-colors relative"
          >
            <Bell className="w-[18px] h-[18px]" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#D4650A]" />
            )}
          </button>

          {notificationOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setNotificationOpen(false)} />
              <div className="absolute right-0 top-full mt-2 w-96 max-h-[480px] overflow-y-auto bg-white rounded-xl border border-[#E7E5E4] shadow-lg z-50">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#F0EFEA]">
                  <span className="text-sm font-semibold text-[#1C1917]">Notifications</span>
                  <button
                    onClick={() => {}}
                    className="text-xs text-[#D4650A] hover:underline"
                  >
                    Mark all read
                  </button>
                </div>
                <div>
                  {notifications.map((notif) => (
                    <div
                      key={notif.id}
                      className={`px-4 py-3 border-b border-[#F0EFEA] hover:bg-[#F5F4F0] cursor-pointer transition-colors ${
                        !notif.read ? 'border-l-[3px] border-l-[#D4650A]' : ''
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                          notif.type === 'success' ? 'bg-[#16A34A]' :
                          notif.type === 'warning' ? 'bg-[#EAB308]' :
                          notif.type === 'error' ? 'bg-[#DC2626]' :
                          'bg-[#2563EB]'
                        }`} />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-[#1C1917] truncate">{notif.title}</div>
                          <div className="text-xs text-[#78716C] mt-0.5 line-clamp-2">{notif.message}</div>
                          <div className="text-[11px] text-[#A8A29E] mt-1">
                            {formatDistanceToNow(new Date(notif.createdAt), { addSuffix: true })}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="px-4 py-2.5 text-center border-t border-[#F0EFEA]">
                  <button className="text-xs text-[#D4650A] hover:underline font-medium">
                    View all notifications
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        <Link
          to="/quotes"
          className="h-9 px-4 flex items-center gap-2 rounded-lg bg-[#D4650A] text-white text-xs font-semibold uppercase tracking-[0.05em] hover:bg-[#B85500] transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New Quote</span>
        </Link>
      </div>
    </header>
  );
}
