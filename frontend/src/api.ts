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
} from "@fplmodell/api-client";
import type { Breakpoint, FixtureTicker, JournalEntry, LineupValue, ScenarioComparison, LoopStatus, ModelCard, PlanRequirement, TeamTimeline } from "@fplmodell/api-client";
import type { CopyCheck, TopCohort, TopManagers, TopManagersStatus } from "@fplmodell/api-client";

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

export interface PageCall { tool: string; args?: Record<string, unknown> }
export interface ChatLine { role: "user" | "assistant"; text: string }
export type ChatEvent =
  | { type: "text" | "status" | "notice"; text: string }
  | { type: "error"; message: string }
  | { type: "done"; usage: Record<string, number> };

/** Server-sent events from POST /chat: status, text deltas, a notice, then done or error. */
async function streamChat(path: string, body: unknown, onEvent: (event: ChatEvent) => void) {
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new Error("Could not contact API. Start the app with .venv/bin/python run_app.py and open http://127.0.0.1:5173.");
  }
  if (!response.ok || !response.body) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail ?? `HTTP ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    events.filter(event => event.startsWith("data: ")).forEach(event => onEvent(JSON.parse(event.slice(6))));
  }
}

export const api = {
  chatHistory(session: string) { return request<{ messages: ChatLine[]; enabled: boolean }>(`/api/team/${session}/chat`); },
  resetChat(session: string) { return request<{ messages: ChatLine[] }>(`/api/team/${session}/chat/reset`, { method: "POST" }); },
  chat(session: string, body: { message: string; page: unknown } & PlayerConstraints, onEvent: (event: ChatEvent) => void) {
    return streamChat(`/api/team/${session}/chat`, body, onEvent);
  },
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
  loopStatus() { return request<LoopStatus>("/api/loop/status"); },
  modelCard() { return request<ModelCard>("/api/model-card"); },
  lockRound() { return request<LoopStatus>("/api/loop/lock", { method: "POST" }); },
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
  plan(session: string, weeks: number, discount = 0.9, constraints?: PlayerConstraints,
       options?: { chips?: boolean; requirements?: PlanRequirement[] }) {
    return request<MultiweekPlan>(`/api/team/${session}/plan`, {
      method: "POST",
      body: JSON.stringify({ weeks, discount, ...constraints, ...options }),
    });
  },
  fixtures(session: string, scope: "squad" | "market" = "squad") { return request<FixtureTicker>(`/api/team/${session}/fixtures?scope=${scope}`); },
  scenarios(session: string, constraints?: PlayerConstraints) {
    return request<ScenarioComparison>(`/api/team/${session}/scenarios`, { method: "POST", body: JSON.stringify({ ...constraints }) });
  },
  breakpoint(session: string, playerId: number, constraints?: PlayerConstraints) {
    return request<Breakpoint>(`/api/team/${session}/scenarios/breakpoint`, { method: "POST", body: JSON.stringify({ ...constraints, player_id: playerId }) });
  },
  journal(session: string) { return request<{ entries: JournalEntry[] }>(`/api/team/${session}/journal`); },
  recordDecision(session: string, choice: JournalEntry["choice"]["kind"], note: string, constraints?: PlayerConstraints) {
    return request<{ entries: JournalEntry[] }>(`/api/team/${session}/journal`, { method: "POST", body: JSON.stringify({ ...constraints, choice, note }) });
  },
  lineupValue(session: string) { return request<LineupValue>(`/api/team/${session}/lineup-value`); },
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
  team(session: string) {
    return request<TeamResponse>(`/api/team/${session}`);
  },
  timeline(session: string) {
    return request<TeamTimeline>(`/api/team/${session}/timeline`);
  },
  topManagers(session: string, cohort: TopCohort) {
    return request<TopManagers>(`/api/team/${session}/top-managers?cohort=${cohort}`);
  },
  topManagersRefresh(session: string) {
    return request<{ status: string }>(`/api/team/${session}/top-managers/refresh`, { method: "POST" });
  },
  copyCheck(session: string, leagueId?: number) {
    return request<CopyCheck>(`/api/team/${session}/copy-check${leagueId ? `?league_id=${leagueId}` : ""}`);
  },
  topManagersStatus() { return request<TopManagersStatus>("/api/top-managers/status"); },
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
