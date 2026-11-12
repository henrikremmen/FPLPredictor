import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Position } from "@fplmodell/shared";
import { waitForJob, type TopCohort } from "@fplmodell/api-client";
import { api } from "../lib/api";
import { useSession } from "../context/session-context";
import { useWorkspace } from "../context/workspace-context";

export function useTransfers(number: number, outgoingIds: number[], enabled = true) {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useQuery({
    queryKey: ["transfers", sessionId, number, outgoingIds, constraints],
    queryFn: () => api.transfers(sessionId as string, number, outgoingIds, constraints),
    enabled: Boolean(sessionId) && enabled,
  });
}

export function useMultiweekPlan(weeks: number, chips = false) {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useQuery({
    queryKey: ["plan", sessionId, weeks, constraints, chips],
    queryFn: () => api.plan(sessionId as string, weeks, 0.9, constraints, { chips }),
    enabled: Boolean(sessionId),
  });
}

export function useChipStrategy() {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useQuery({
    queryKey: ["chips", sessionId, constraints],
    queryFn: () => api.chips(sessionId as string, constraints),
    enabled: Boolean(sessionId),
  });
}

export function useRecommendedSquads() {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useQuery({
    queryKey: ["recommended-squads", sessionId, constraints],
    queryFn: () => api.recommendedSquads(sessionId as string, constraints),
    enabled: Boolean(sessionId),
  });
}

export function useStrategyAdvice() {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useQuery({
    queryKey: ["strategy", sessionId, constraints],
    queryFn: () => api.strategy(sessionId as string, constraints),
    enabled: Boolean(sessionId),
  });
}

/** Hold versus buy, after selling price, bank and any hit (runs on demand). */
export function useComparePlayers() {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  return useMutation({
    mutationFn: ({ outId, inId }: { outId: number; inId: number }) =>
      api.compare(sessionId as string, outId, inId, constraints),
  });
}

export function useMarket(position: Position | "ALL", maxPrice: number) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["market", sessionId, position, maxPrice],
    queryFn: () => api.market(sessionId as string, position, maxPrice),
    enabled: Boolean(sessionId),
  });
}

export function useSellCandidates() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["sells", sessionId],
    queryFn: () => api.sells(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useAnalytics(event?: number, leagueId?: number | null) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["analytics", sessionId, event, leagueId],
    queryFn: () => api.analytics(sessionId as string, event, leagueId),
    enabled: Boolean(sessionId),
  });
}

export function useTopManagers(cohort: TopCohort) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["top-managers", sessionId, cohort],
    queryFn: () => api.topManagers(sessionId as string, cohort),
    enabled: Boolean(sessionId),
  });
}

export function useCopyCheck(leagueId?: number) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["copy-check", sessionId, leagueId],
    queryFn: () => api.copyCheck(sessionId as string, leagueId),
    enabled: Boolean(sessionId),
  });
}

export function useTimeline() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["timeline", sessionId],
    queryFn: () => api.timeline(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useRefreshForecast() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await api.refreshForecast();
      return waitForJob(() => api.forecastStatus());
    },
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}

/** Pull-to-refresh for a tab: refetch the queries currently on screen. */
export function usePullToRefresh() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({ refetchType: "active" });
    } finally {
      setRefreshing(false);
    }
  };
  return { refreshing, onRefresh };
}

/** Plan P3: XI forecast against the expectation with autosubs and vice-captain. */
export function useLineupValue() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["lineup-value", sessionId],
    queryFn: () => api.lineupValue(sessionId as string),
    enabled: Boolean(sessionId),
  });
}
