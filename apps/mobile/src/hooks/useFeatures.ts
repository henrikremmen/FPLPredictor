import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Position } from "@fplmodell/shared";
import { api } from "../lib/api";
import { useSession } from "../context/session-context";

export function useTransfers(number: number, outgoingIds: number[], enabled = true) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["transfers", sessionId, number, outgoingIds],
    queryFn: () => api.transfers(sessionId as string, number, outgoingIds),
    enabled: Boolean(sessionId) && enabled,
  });
}

export function useMultiweekPlan(weeks: number) {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["plan", sessionId, weeks],
    queryFn: () => api.plan(sessionId as string, weeks),
    enabled: Boolean(sessionId),
  });
}

export function useChipStrategy() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["chips", sessionId],
    queryFn: () => api.chips(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useRecommendedSquads() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["recommended-squads", sessionId],
    queryFn: () => api.recommendedSquads(sessionId as string),
    enabled: Boolean(sessionId),
  });
}

export function useStrategyAdvice() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["strategy", sessionId],
    queryFn: () => api.strategy(sessionId as string),
    enabled: Boolean(sessionId),
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

export function useRefreshForecast() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.refreshForecast(),
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}
