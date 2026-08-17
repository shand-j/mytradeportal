import { QueryClient } from "@tanstack/react-query";
import { ApiError, NetworkError } from "./apiClient";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (failureCount, error) => {
        // Don't retry auth/permission errors or when we're offline; those won't
        // succeed on retry and would just delay the fallback UI.
        if (error instanceof NetworkError) return false;
        if (error instanceof ApiError && [400, 401, 403, 404].includes(error.status)) {
          return false;
        }
        return failureCount < 2;
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});
