import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RiskProfile } from "@fplmodell/shared";
import { waitForJob, type SquadChange } from "@fplmodell/api-client";
import { api } from "../lib/api";
import { loadTeam } from "../lib/team-session";
import { useSession } from "../context/session-context";

export function teamQueryKey(sessionId: string | null) {
  return ["team", sessionId] as const;
}

export function useTeam() {
  const queryClient = useQueryClient();
  const { sessionId, fplId, horizon, riskProfile, setSessionId } = useSession();
  return useQuery({
    queryKey: teamQueryKey(sessionId),
    queryFn: async () => {
      const { team, replaced } = await loadTeam(api, sessionId as string, { fplId, horizon, riskProfile });
      if (replaced) {
        queryClient.setQueryData(teamQueryKey(team.session_id), team);
        await setSessionId(team.session_id);
      }
      return team;
    },
    enabled: Boolean(sessionId),
  });
}

export function useImportTeam() {
  const queryClient = useQueryClient();
  const { completeOnboarding } = useSession();
  return useMutation({
    mutationFn: (input: { reference: string; horizon: number; riskProfile: RiskProfile }) =>
      api.importTeam(input.reference, input.horizon, input.riskProfile),
    onSuccess: async (team, variables) => {
      await completeOnboarding({
        fplId: variables.reference,
        horizon: variables.horizon,
        riskProfile: variables.riskProfile,
        sessionId: team.session_id,
      });
      queryClient.setQueryData(teamQueryKey(team.session_id), team);
    },
  });
}

export function useRefreshTeam() {
  const queryClient = useQueryClient();
  const { sessionId } = useSession();
  return useMutation({
    mutationFn: async () => {  // the update runs on the server; poll it, then read the reloaded team
      await api.refreshTeam(sessionId as string);
      await waitForJob(() => api.forecastStatus());
      return api.getTeam(sessionId as string);
    },
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryKey(sessionId), team);
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  const { sessionId } = useSession();
  return useMutation({
    mutationFn: (input: { bank: number; freeTransfers: number }) =>
      api.updateSettings(sessionId as string, input.bank, input.freeTransfers),
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryKey(sessionId), team);
    },
  });
}

export function useUpdateSquad() {
  const queryClient = useQueryClient();
  const { sessionId } = useSession();
  return useMutation({
    mutationFn: (input: {
      mode: "synchronize" | "apply_transfers";
      changes: SquadChange[];
      bank?: number;
      freeTransfers?: number;
    }) => api.updateSquad(sessionId as string, input.mode, input.changes, input.bank, input.freeTransfers),
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryKey(sessionId), team);
    },
  });
}

export function useResetSquad() {
  const queryClient = useQueryClient();
  const { sessionId } = useSession();
  return useMutation({
    mutationFn: () => api.resetSquad(sessionId as string),
    onSuccess: (team) => {
      queryClient.setQueryData(teamQueryKey(sessionId), team);
    },
  });
}

export function useSquadOptions() {
  const { sessionId } = useSession();
  return useQuery({
    queryKey: ["squad-options", sessionId],
    queryFn: () => api.squadOptions(sessionId as string),
    enabled: Boolean(sessionId),
  });
}
