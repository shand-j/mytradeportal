import { useEffect } from 'react';
import { Sparkles, Phone, TrendingUp } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { useAiInsights, useFeatureFlags } from '@/lib/api/hooks';
import { useUiStore } from '@/stores/uiStore';

export function AiInsights() {
  const setPageTitle = useUiStore(s => s.setPageTitle);
  const { data, isLoading, error } = useAiInsights();
  const { data: featureFlags } = useFeatureFlags();
  // Voice analytics and demand forecasting are not yet implemented; the
  // cards stay hidden until their feature flags are enabled in Railway.
  const voiceAiEnabled = featureFlags?.voiceAiInsights === true;
  const demandForecastingEnabled = featureFlags?.demandForecasting === true;

  useEffect(() => {
    setPageTitle('AI Insights');
  }, [setPageTitle]);

  if (isLoading) return <div className="space-y-4"><div className="bg-white rounded-xl h-64 animate-pulse" /><div className="bg-white rounded-xl h-64 animate-pulse" /></div>;

  if (error) return <div className="text-center py-12 text-[#DC2626]">Failed to load AI insights</div>;

  if (!data) return <div className="space-y-4"><div className="bg-white rounded-xl h-64 animate-pulse" /><div className="bg-white rounded-xl h-64 animate-pulse" /></div>;

  const { aiQuotePerformance, voiceAnalytics, demandForecast } = data;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Sparkles className="w-6 h-6 text-[#7C3AED]" />
        <h1 className="text-xl font-semibold text-[#1C1917]">AI Insights</h1>
        <span className="px-2 py-0.5 bg-[#F5F3FF] rounded-full text-[11px] font-medium text-[#7C3AED]">Powered by AI</span>
      </div>

      {/* Quote Performance */}
      <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-[#1C1917]">AI Quote Performance</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          <div className="text-center p-3 bg-[#F5F4F0] rounded-lg">
            <div className="text-2xl font-bold text-[#1C1917]">{aiQuotePerformance.totalGenerated}</div>
            <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">Quotes Generated</div>
          </div>
          <div className="text-center p-3 bg-[#F0FDF4] rounded-lg">
            <div className="text-2xl font-bold text-[#16A34A]">{aiQuotePerformance.acceptanceRate}%</div>
            <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">Acceptance Rate</div>
          </div>
          <div className="text-center p-3 bg-[#FFF7ED] rounded-lg">
            <div className="text-2xl font-bold text-[#D4650A]">£{aiQuotePerformance.averageValue}</div>
            <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">Avg Value</div>
          </div>
          <div className="text-center p-3 bg-[#EFF6FF] rounded-lg">
            <div className="text-2xl font-bold text-[#2563EB]">{aiQuotePerformance.averageGenerationTime}s</div>
            <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">Avg Generation</div>
          </div>
          {aiQuotePerformance.editRate != null && (
            <div className="text-center p-3 bg-[#F5F4F0] rounded-lg">
              <div className="text-2xl font-bold text-[#1C1917]">{Math.round(aiQuotePerformance.editRate * 100)}%</div>
              <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">AI Drafts Edited</div>
            </div>
          )}
          {aiQuotePerformance.avgPriceDriftPct != null && (
            <div className="text-center p-3 bg-[#F5F4F0] rounded-lg">
              <div className="text-2xl font-bold text-[#1C1917]">{aiQuotePerformance.avgPriceDriftPct}%</div>
              <div className="text-[11px] text-[#78716C] uppercase tracking-[0.05em]">Avg Price Adjustment</div>
            </div>
          )}
        </div>
        <div className="h-[250px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={aiQuotePerformance.monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F0EFEA" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ background: 'white', border: '1px solid #E7E5E4', borderRadius: '8px' }} />
              <Bar dataKey="aiQuotes" fill="#7C3AED" radius={[4, 4, 0, 0]} name="AI Quotes" />
              <Bar dataKey="manualQuotes" fill="#E7E5E4" radius={[4, 4, 0, 0]} name="Manual Quotes" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Voice Analytics */}
      {voiceAiEnabled && voiceAnalytics && (
      <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <Phone className="w-5 h-5 text-[#2563EB]" />
          <h3 className="text-lg font-semibold text-[#1C1917]">Voice Agent Activity</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
          <div className="text-center p-3 bg-[#F5F4F0] rounded-lg">
            <div className="text-2xl font-bold text-[#1C1917]">{voiceAnalytics.totalCalls}</div>
            <div className="text-[11px] text-[#78716C]">Calls Handled</div>
          </div>
          <div className="text-center p-3 bg-[#EFF6FF] rounded-lg">
            <div className="text-2xl font-bold text-[#2563EB]">{voiceAnalytics.averageDuration}</div>
            <div className="text-[11px] text-[#78716C]">Avg Duration</div>
          </div>
          <div className="text-center p-3 bg-[#F0FDF4] rounded-lg">
            <div className="text-2xl font-bold text-[#16A34A]">{voiceAnalytics.resolutionRate}%</div>
            <div className="text-[11px] text-[#78716C]">Resolution Rate</div>
          </div>
          <div className="text-center p-3 bg-[#FFF7ED] rounded-lg">
            <div className="text-2xl font-bold text-[#D4650A]">£{voiceAnalytics.totalRevenue}</div>
            <div className="text-[11px] text-[#78716C]">Revenue</div>
          </div>
        </div>
      </div>
      )}

      {/* Demand Forecast */}
      {demandForecastingEnabled && demandForecast && (
        <div className="bg-white rounded-xl border border-[#E7E5E4] p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-[#16A34A]" />
            <h3 className="text-lg font-semibold text-[#1C1917]">Demand Forecast</h3>
          </div>
          <div className="h-[200px] mb-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={demandForecast.predictions}>
                <defs>
                  <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#16A34A" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#16A34A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0EFEA" vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: '#78716C' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: 'white', border: '1px solid #E7E5E4', borderRadius: '8px' }} />
                <Area type="monotone" dataKey="predictedJobs" stroke="#16A34A" strokeWidth={2} fill="url(#forecastGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="bg-[#F5F3FF] border border-[#EDE9FE] rounded-lg p-4">
            <div className="flex items-start gap-2">
              <Sparkles className="w-4 h-4 text-[#7C3AED] mt-0.5 flex-shrink-0" />
              <p className="text-sm text-[#1C1917]">{demandForecast.insight}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
