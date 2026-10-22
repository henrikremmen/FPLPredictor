import type {
  PlayerConstraints, PlayerDetail, PlayerComparison, SnapshotChanges, RefreshStatus,
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
      "Could not contact API. Start the app with .venv/bin/python run_app.py and open http://127.0.0.1:5173.",
    );
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }
  return payload as T;
}

export const api = {
  player(session: string, id: number) {
    return request<PlayerDetail>(`/api/team/${session}/players/${id}`);
  },
  changes(session: string) {
    return request<SnapshotChanges>(`/api/team/${session}/changes`);
  },
  compare(session: string, outId: number, inId: number, constraints: PlayerConstraints) {
    return request<PlayerComparison>(`/api/team/${session}/compare`, {
      method: "POST", body: JSON.stringify({ out_id: outId, in_id: inId, ...constraints }),
    });
  },
  refreshStatus() { return request<RefreshStatus>("/api/forecast/status"); },
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
  updateHorizon(session: string, horizon: number) {
    return request<TeamResponse>(`/api/team/${session}/horizon`, {
      method: "PATCH", body: JSON.stringify({ horizon }),
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
  transfers(session: string, number: number, outgoingIds: number[] = [], constraints?: PlayerConstraints) {
    return request<TransferResponse>(`/api/team/${session}/transfers`, {
      method: "POST",
      body: JSON.stringify({ number, outgoing_ids: outgoingIds, ...constraints }),
    });
  },
  plan(session: string, weeks: number, discount = 0.9, constraints?: PlayerConstraints) {
    return request<MultiweekPlan>(`/api/team/${session}/plan`, {
      method: "POST",
      body: JSON.stringify({ weeks, discount, ...constraints }),
    });
  },
  chips(session: string, constraints?: PlayerConstraints) {
    return request<ChipStrategy>(`/api/team/${session}/chips`, { method: "POST", body: JSON.stringify(constraints ?? {}) });
  },
  recommendedSquads(session: string, constraints?: PlayerConstraints) {
    return request<RecommendedSquads>(`/api/team/${session}/recommended-squads`, {
      method: "POST", body: JSON.stringify(constraints ?? {}),
    });
  },
  strategy(session: string, constraints?: PlayerConstraints) {
    return request<StrategyAdvice>(`/api/team/${session}/strategy`, { method: "POST", body: JSON.stringify(constraints ?? {}) });
  },
  analytics(session: string, event?: number, leagueId?: number | null) {
    const params = new URLSearchParams();
    if (event != null) params.set("event", String(event));
    if (leagueId != null) params.set("league_id", String(leagueId));
    const query = params.size ? `?${params}` : "";
    return request<ManagerAnalytics>(`/api/team/${session}/analytics${query}`);
  },
  async market(session: string, position: Position | "ALL", maxPrice: number, constraints?: PlayerConstraints) {
    const params = new URLSearchParams({ limit: "30", max_price: String(maxPrice) });
    if (position !== "ALL") params.set("position", position);
    constraints?.locked_ids.forEach(id => params.append("locked_ids", String(id)));
    constraints?.excluded_ids.forEach(id => params.append("excluded_ids", String(id)));
    return request<{ players: Player[] }>(`/api/team/${session}/market?${params}`);
  },
  async sells(session: string, constraints?: PlayerConstraints) {
    const params = new URLSearchParams();
    constraints?.locked_ids.forEach(id => params.append("locked_ids", String(id)));
    constraints?.excluded_ids.forEach(id => params.append("excluded_ids", String(id)));
    return request<{ players: Player[] }>(`/api/team/${session}/sells?${params}`);
  },
  refreshForecast() {
    return request<{ status: string }>("/api/forecast/refresh", { method: "POST" });
  },
  refreshTeam(session: string) {
    return request<TeamResponse>(`/api/team/${session}/refresh`, { method: "POST" });
  },
};
