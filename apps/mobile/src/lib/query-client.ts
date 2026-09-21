import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@fplmodell/api-client";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        // Retrying a dead backend or a timeout just burns battery and delays
        // the error state the user actually needs to see.
        if (error instanceof ApiError && (error.kind === "network" || error.kind === "timeout")) {
          return false;
        }
        return failureCount < 2;
      },
      staleTime: 30_000,
    },
    mutations: {
      retry: false,
    },
  },
});
