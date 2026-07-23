import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { ApiError } from '@/lib/api/client';

/**
 * Feature flags returned by `GET /feature-flags`.
 *
 * The API client camelizes response keys, so the snake_case Railway Signals
 * flag names (`voice_ai_insights`, …) arrive here as camelCase. Flags are
 * project-scoped and default to `false` server-side when absent from the
 * Railway registry, so gated features stay off unless explicitly enabled.
 * Unknown flags pass through the index signature so new flags can be adopted
 * without a type change.
 */
export interface FeatureFlags {
  voiceAiInsights: boolean;
  demandForecasting: boolean;
  externalIntegrations: boolean;
  [flag: string]: boolean;
}

const featureFlagsKeys = {
  all: ['feature-flags'] as const,
};

export function useFeatureFlags() {
  return useQuery<FeatureFlags, ApiError>({
    queryKey: featureFlagsKeys.all,
    // Fail open to an empty map: every flag then reads as falsy (off).
    queryFn: () => api.get<FeatureFlags>('/feature-flags').catch(() => ({}) as FeatureFlags),
    staleTime: 60_000,
  });
}
