import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

type FeatureFlagsResponse = {
  paddleBilling?: boolean;
};

type FeatureFlags = {
  paddleBilling: boolean;
};

const DEFAULT_FLAGS: FeatureFlags = {
  paddleBilling: false,
};

export async function getFeatureFlags(): Promise<FeatureFlags> {
  try {
    const flags = await api.get<FeatureFlagsResponse>("/feature-flags", { auth: false });
    return {
      ...DEFAULT_FLAGS,
      ...flags,
    };
  } catch {
    return DEFAULT_FLAGS;
  }
}

export function useFeatureFlags() {
  return useQuery({
    queryKey: ["feature-flags"],
    queryFn: getFeatureFlags,
    staleTime: 60_000,
  });
}
