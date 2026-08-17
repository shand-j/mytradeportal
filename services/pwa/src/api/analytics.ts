import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { config } from "../lib/config";

/** Subset of the backend dashboard KPIs the analytics screen needs. */
export type ApiDashboardKpis = {
  revenueThisMonth: number;
  revenueChange: number;
  activeJobs: number;
  pendingQuotes: number;
  pendingQuotesValue: number;
};

type ApiDashboard = {
  kpi: ApiDashboardKpis;
};

export async function fetchDashboard(): Promise<ApiDashboard> {
  return api.get<ApiDashboard>("/analytics/dashboard");
}

/**
 * Real revenue KPIs for the analytics screen. In connected mode this is the
 * backend's paid-invoice revenue; otherwise the caller uses its mock figures.
 */
export function useDashboardKpis() {
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    enabled: config.apiEnabled,
  });

  return {
    kpi: query.data?.kpi,
    isConnected: config.apiEnabled && query.isSuccess,
    isLoading: config.apiEnabled && query.isLoading,
  };
}
