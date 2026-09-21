import type {
  ChipStrategy,
  RecommendedSquads,
  Position,
  RiskProfile,
  TeamResponse,
  TransferResponse,
  MultiweekPlan,
  Player,
  StrategyAdvice,
  ManagerAnalytics,
  SquadChange,
  SquadUpdateResponse,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch {
    throw new Error(
      "Kunne ikke kontakte API-et. Start appen med .venv/bin/python run_app.py og åpne http://127.0.0.1:5173.",
    );
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }
  return payload as T;
}

export const api = {
  importTeam(reference: string, horizon: number, riskProfile: RiskProfile) {
    return request<TeamResponse>("/api/team/import", {
      method: "POST",
      body: JSON.stringify({ reference, horizon, risk_profile: riskProfile }),
    });
  },
  updateSettings(session: string, bank: number, freeTransfers: number) {
    return request<TeamResponse>(`/api/team/${session}/settings`, {
      method: "PATCH",
      body: JSON.stringify({ bank, free_transfers: freeTransfers }),
    });
  },
  squadOptions(session: string) {
    return request<{ players: Player[] }>(`/api/team/${session}/squad-options`);
  },
  updateSquad(
    session: string,
    mode: "synchronize" | "apply_transfers",
    changes: SquadChange[],
    bank?: number,
    freeTransfers?: number,
  ) {
    return request<SquadUpdateResponse>(`/api/team/${session}/squad`, {
      method: "PATCH",
      body: JSON.stringify({
        mode,
        changes,
        bank: mode === "synchronize" ? bank : null,
        free_transfers: mode === "synchronize" ? freeTransfers : null,
      }),
    });
  },
  resetSquad(session: string) {
    return request<TeamResponse>(`/api/team/${session}/squad/reset`, { method: "POST" });
  },
  transfers(session: string, number: number, outgoingIds: number[] = []) {
    return request<TransferResponse>(`/api/team/${session}/transfers`, {
      method: "POST",
      body: JSON.stringify({ number, outgoing_ids: outgoingIds }),
    });
  },
  plan(session: string, weeks: number, discount = 0.9) {
    return request<MultiweekPlan>(`/api/team/${session}/plan`, {
      method: "POST",
      body: JSON.stringify({ weeks, discount }),
    });
  },
  chips(session: string) {
    return request<ChipStrategy>(`/api/team/${session}/chips`, { method: "POST" });
  },
  recommendedSquads(session: string) {
    return request<RecommendedSquads>(`/api/team/${session}/recommended-squads`, {
      method: "POST",
    });
  },
  strategy(session: string) {
    return request<StrategyAdvice>(`/api/team/${session}/strategy`, { method: "POST" });
  },
  analytics(session: string, event?: number, leagueId?: number | null) {
    const params = new URLSearchParams();
    if (event != null) params.set("event", String(event));
    if (leagueId != null) params.set("league_id", String(leagueId));
    const query = params.size ? `?${params}` : "";
    return request<ManagerAnalytics>(`/api/team/${session}/analytics${query}`);
  },
  async market(session: string, position: Position | "ALL", maxPrice: number) {
    const params = new URLSearchParams({ limit: "30", max_price: String(maxPrice) });
    if (position !== "ALL") params.set("position", position);
    return request<{ players: Player[] }>(`/api/team/${session}/market?${params}`);
  },
  async sells(session: string) {
    return request<{ players: Player[] }>(`/api/team/${session}/sells`);
  },
  refreshForecast() {
    return request<{ status: string }>("/api/forecast/refresh", { method: "POST" });
  },
  refreshTeam(session: string) {
    return request<TeamResponse>(`/api/team/${session}/refresh`, { method: "POST" });
  },
};
