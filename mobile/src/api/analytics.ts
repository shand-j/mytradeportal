import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

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

/** Real revenue KPIs for the analytics screen from the backend's dashboard endpoint. */
export function useDashboardKpis() {
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
  });

  return {
    kpi: query.data?.kpi,
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}
