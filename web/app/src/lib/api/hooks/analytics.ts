import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';
import type { AiInsightsData, DashboardData } from '@/types';

const analyticsKeys = {
  dashboard: ['dashboard'] as const,
  aiInsights: ['analytics', 'ai-insights'] as const,
};

export function useDashboard() {
  return useQuery<DashboardData, ApiError>({
    queryKey: analyticsKeys.dashboard,
    queryFn: () => api.get('/analytics/dashboard'),
  });
}

export function useAiInsights() {
  return useQuery<AiInsightsData, ApiError>({
    queryKey: analyticsKeys.aiInsights,
    queryFn: () => api.get('/analytics/ai-insights'),
  });
}
