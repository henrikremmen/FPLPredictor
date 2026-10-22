import type {
  ChipStrategy,
  HealthResponse,
  ManagerAnalytics,
  MultiweekPlan,
  Player,
  RecommendedSquads,
  RiskProfile,
  SquadChange,
  SquadUpdateResponse,
  StrategyAdvice,
  TeamResponse,
  TeamTimeline,
  PlayerComparison,
  PlayerConstraints,
  TransferResponse,
} from "./types";

export type ApiErrorKind = "network" | "timeout" | "http";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

export interface ApiClientOptions {
  baseUrl: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

const DEFAULT_TIMEOUT_MS = 15_000;
const REFRESH_TIMEOUT_MS = 120_000;

/**
 * Thin fetch client for the FastAPI bridge (src/api.py). No API keys ever
 * live here or in any caller of this client — the backend holds every
 * external credential and this client only ever talks to that backend.
 */
export class ApiClient {
  private baseUrl: string;
  private timeoutMs: number;
  private fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    // Browsers reject window.fetch called with another `this` ("Illegal invocation").
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  }

  private async request<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
    const controller = new AbortController();
    const timeoutMs = options?.timeoutMs ?? this.timeoutMs;
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...options?.headers },
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new ApiError("timeout", `Request timed out: ${this.baseUrl}${path}.`);
      }
      throw new ApiError(
        "network",
        `Could not contact the API on ${this.baseUrl}. Check that the backend is running and your phone is on the same network.`,
      );
    } finally {
      clearTimeout(timer);
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new ApiError("http", payload?.detail ?? `HTTP ${response.status}`, response.status);
    }
    return payload as T;
  }

  health() {
    return this.request<HealthResponse>("/api/health");
  }

  importTeam(reference: string, horizon: number, riskProfile: RiskProfile) {
    return this.request<TeamResponse>("/api/team/import", {
      method: "POST",
      body: JSON.stringify({ reference, horizon, risk_profile: riskProfile }),
    });
  }

  getTeam(session: string) {
    return this.request<TeamResponse>(`/api/team/${session}`);
  }

  updateSettings(session: string, bank: number, freeTransfers: number) {
    return this.request<TeamResponse>(`/api/team/${session}/settings`, {
      method: "PATCH",
      body: JSON.stringify({ bank, free_transfers: freeTransfers }),
    });
  }

  squadOptions(session: string) {
    return this.request<{ players: Player[] }>(`/api/team/${session}/squad-options`);
  }

  updateSquad(
    session: string,
    mode: "synchronize" | "apply_transfers",
    changes: SquadChange[],
    bank?: number,
    freeTransfers?: number,
  ) {
    return this.request<SquadUpdateResponse>(`/api/team/${session}/squad`, {
      method: "PATCH",
      body: JSON.stringify({
        mode,
        changes,
        bank: mode === "synchronize" ? bank : null,
        free_transfers: mode === "synchronize" ? freeTransfers : null,
      }),
    });
  }

  resetSquad(session: string) {
    return this.request<TeamResponse>(`/api/team/${session}/squad/reset`, { method: "POST" });
  }

  /** Locked/excluded players apply inside every optimiser, as on the web. */
  transfers(session: string, number: number, outgoingIds: number[] = [], constraints?: PlayerConstraints) {
    return this.request<TransferResponse>(`/api/team/${session}/transfers`, {
      method: "POST",
      body: JSON.stringify({ number, outgoing_ids: outgoingIds, ...constraints }),
    });
  }

  plan(session: string, weeks: number, discount = 0.9, constraints?: PlayerConstraints) {
    return this.request<MultiweekPlan>(`/api/team/${session}/plan`, {
      method: "POST",
      body: JSON.stringify({ weeks, discount, ...constraints }),
    });
  }

  chips(session: string, constraints?: PlayerConstraints) {
    return this.request<ChipStrategy>(`/api/team/${session}/chips`, { method: "POST", body: JSON.stringify(constraints ?? {}) });
  }

  recommendedSquads(session: string, constraints?: PlayerConstraints) {
    return this.request<RecommendedSquads>(`/api/team/${session}/recommended-squads`, {
      method: "POST", body: JSON.stringify(constraints ?? {}),
    });
  }

  strategy(session: string, constraints?: PlayerConstraints) {
    return this.request<StrategyAdvice>(`/api/team/${session}/strategy`, { method: "POST", body: JSON.stringify(constraints ?? {}) });
  }

  /** Hold one player versus buying another, after selling price, bank and hits. */
  compare(session: string, outId: number, inId: number, constraints?: PlayerConstraints) {
    return this.request<PlayerComparison>(`/api/team/${session}/compare`, {
      method: "POST", body: JSON.stringify({ out_id: outId, in_id: inId, ...constraints }),
    });
  }

  analytics(session: string, event?: number, leagueId?: number | null) {
    const params = new URLSearchParams();
    if (event != null) params.set("event", String(event));
    if (leagueId != null) params.set("league_id", String(leagueId));
    const query = params.size ? `?${params}` : "";
    return this.request<ManagerAnalytics>(`/api/team/${session}/analytics${query}`);
  }

  timeline(session: string) {
    return this.request<TeamTimeline>(`/api/team/${session}/timeline`);
  }

  market(session: string, position: "GK" | "DEF" | "MID" | "FWD" | "ALL", maxPrice: number) {
    const params = new URLSearchParams({ limit: "30", max_price: String(maxPrice) });
    if (position !== "ALL") params.set("position", position);
    return this.request<{ players: Player[] }>(`/api/team/${session}/market?${params}`);
  }

  sells(session: string) {
    return this.request<{ players: Player[] }>(`/api/team/${session}/sells`);
  }

  refreshForecast() {
    return this.request<{ status: string }>("/api/forecast/refresh", {
      method: "POST",
      timeoutMs: REFRESH_TIMEOUT_MS,
    });
  }

  refreshTeam(session: string) {
    return this.request<TeamResponse>(`/api/team/${session}/refresh`, {
      method: "POST",
      timeoutMs: REFRESH_TIMEOUT_MS,
    });
  }
}
