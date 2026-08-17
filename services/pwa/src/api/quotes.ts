import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";
import { config } from "../lib/config";

/** Subset of the backend Quote shape the dashboard needs (camelized). */
export type ApiQuote = {
  id: string;
  title: string;
  status: string;
  total: string;
};

export async function fetchQuotes(): Promise<ApiQuote[]> {
  return api.get<ApiQuote[]>("/quotes");
}

/**
 * Outstanding-quotes total for the dashboard.
 *
 * In connected mode this comes from the real backend (`GET /quotes`, summing
 * draft + sent). In demo/offline mode the query is disabled and the caller
 * uses its mock figure instead. `source` lets the UI show a subtle "Live" badge.
 */
export function useOutstandingQuotes() {
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: fetchQuotes,
    enabled: config.apiEnabled,
  });

  const total = (query.data ?? [])
    .filter((q) => q.status === "draft" || q.status === "sent")
    .reduce((sum, q) => sum + (parseFloat(q.total) || 0), 0);

  return {
    total,
    count: query.data?.length ?? 0,
    isConnected: config.apiEnabled && query.isSuccess,
    isLoading: query.isLoading,
  };
}
