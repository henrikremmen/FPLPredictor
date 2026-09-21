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
    this.fetchImpl = options.fetchImpl ?? fetch;
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
        throw new ApiError("timeout", `Tidsavbrudd mot ${this.baseUrl}${path}.`);
      }
      throw new ApiError(
        "network",
        `Kunne ikke kontakte API-et på ${this.baseUrl}. Sjekk at backend kjører og at telefonen er på samme nettverk.`,
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

  transfers(session: string, number: number, outgoingIds: number[] = []) {
    return this.request<TransferResponse>(`/api/team/${session}/transfers`, {
      method: "POST",
      body: JSON.stringify({ number, outgoing_ids: outgoingIds }),
    });
  }

  plan(session: string, weeks: number, discount = 0.9) {
    return this.request<MultiweekPlan>(`/api/team/${session}/plan`, {
      method: "POST",
      body: JSON.stringify({ weeks, discount }),
    });
  }

  chips(session: string) {
    return this.request<ChipStrategy>(`/api/team/${session}/chips`, { method: "POST" });
  }

  recommendedSquads(session: string) {
    return this.request<RecommendedSquads>(`/api/team/${session}/recommended-squads`, { method: "POST" });
  }

  strategy(session: string) {
    return this.request<StrategyAdvice>(`/api/team/${session}/strategy`, { method: "POST" });
  }

  analytics(session: string, event?: number, leagueId?: number | null) {
    const params = new URLSearchParams();
    if (event != null) params.set("event", String(event));
    if (leagueId != null) params.set("league_id", String(leagueId));
    const query = params.size ? `?${params}` : "";
    return this.request<ManagerAnalytics>(`/api/team/${session}/analytics${query}`);
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
