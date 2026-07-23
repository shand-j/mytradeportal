import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ToastContainer } from './ToastContainer';
import { VoiceAgentWidget } from '@/components/shared/VoiceAgentWidget';
import { useFeatureFlags } from '@/lib/api/hooks';

export function AppShell() {
  const location = useLocation();
  const { data: featureFlags } = useFeatureFlags();
  // Voice AI is not yet implemented; the widget stays hidden until the
  // `voice_ai_insights` feature flag is enabled in Railway.
  const voiceAiEnabled = featureFlags?.voiceAiInsights === true;

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#F8F7F4]">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 transition-all duration-300">
        <TopBar />
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6">
          <div
            key={location.pathname}
            className="animate-fadeIn"
          >
            <Outlet />
          </div>
        </main>
      </div>
      <ToastContainer />
      {voiceAiEnabled && <VoiceAgentWidget />}
    </div>
  );
}
